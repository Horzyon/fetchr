import asyncio
import subprocess
import json
import uuid
import time
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import init_db, create_user, get_user_by_email, get_user_by_id
from auth import hash_password, verify_password, create_token, decode_token

app = FastAPI(title="Grab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = Path("/tmp/grab")
TEMP_DIR.mkdir(exist_ok=True)

# Stocke les sessions de pré-fetch actives
# session_id -> {path_video, path_audio, meta, created_at, downloaded}
sessions: dict[str, dict] = {}

CLEANUP_DELAY = 150  # 2min30 après le dernier download


# --- Auth models ---

class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


# --- Auth helpers ---

async def _get_current_user(authorization: Optional[str] = None) -> dict | None:
    """Extract and validate Bearer token, return user dict or None."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    user_id = decode_token(token)
    if user_id is None:
        return None
    user = await get_user_by_id(user_id)
    return user


# --- Auth endpoints ---

@app.post("/auth/register")
async def register(req: RegisterRequest):
    existing = await get_user_by_email(req.email)
    if existing:
        raise HTTPException(409, "Un compte avec cet email existe deja")

    hashed = hash_password(req.password)
    try:
        user = await create_user(req.email, req.username, hashed)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, "Email ou username deja pris")
        raise HTTPException(500, "Erreur creation compte")

    token = create_token(user["id"])
    return {"token": token, "user": user}


@app.post("/auth/login")
async def login(req: LoginRequest):
    user = await get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Email ou mot de passe incorrect")

    token = create_token(user["id"])
    return {
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "is_pro": bool(user["is_pro"]),
            "api_token": user["api_token"],
        },
    }


@app.get("/auth/me")
async def me(authorization: Optional[str] = Header(None)):
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Token invalide ou expire")
    return {
        "id": user["id"],
        "email": user["email"],
        "username": user["username"],
        "is_pro": bool(user["is_pro"]),
        "api_token": user["api_token"],
        "pro_expires_at": user["pro_expires_at"],
    }


@app.post("/auth/refresh")
async def refresh(authorization: Optional[str] = Header(None)):
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Token invalide ou expire")
    token = create_token(user["id"])
    return {"token": token}


# --- Download models ---

class PrepareRequest(BaseModel):
    url: str
    pro: bool = False


class ConvertRequest(BaseModel):
    session_id: str
    format: str  # "video" ou "audio"
    quality: str  # "4k", "1080p", "720p", "480p", "flac", "mp3_320", "mp3_128", "m4a_128"


@app.post("/prepare")
async def prepare(req: PrepareRequest, authorization: Optional[str] = Header(None)):
    # Determine pro status from auth token if present
    pro = False
    user = await _get_current_user(authorization)
    if user and bool(user["is_pro"]):
        pro = True

    session_id = str(uuid.uuid4())[:8]
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(exist_ok=True)

    meta = await _fetch_meta(req.url)
    if not meta:
        raise HTTPException(400, "URL invalide ou non supportée")

    sessions[session_id] = {
        "dir": str(session_dir),
        "meta": meta,
        "url": req.url,
        "pro": pro,
        "video_ready": False,
        "audio_ready": False,
        "created_at": time.time(),
        "last_download": None,
    }

    asyncio.create_task(_prefetch(session_id, req.url, pro, session_dir))

    return {
        "session_id": session_id,
        "title": meta.get("title"),
        "thumbnail": meta.get("thumbnail"),
        "duration": meta.get("duration_string"),
        "views": meta.get("view_count"),
    }


@app.post("/download")
async def download(req: ConvertRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session expirée ou invalide")

    session_dir = Path(session["dir"])
    pro = session["pro"]
    url = session["url"]

    if req.format == "video":
        # Max quality = use prefetch (instant)
        max_quality = "4k" if pro else "1080p"
        if req.quality == max_quality:
            if not session["video_ready"]:
                for _ in range(60):
                    await asyncio.sleep(1)
                    if session["video_ready"]:
                        break
                else:
                    raise HTTPException(504, "Pré-fetch vidéo timeout")
            output = await _get_prefetch_video(session, session_dir, pro)
        else:
            # Lower quality = download direct from source (no ffmpeg re-encode)
            output = await _download_video_direct(url, req.quality, session_dir)

    elif req.format == "audio":
        # Max quality = use prefetch
        max_quality = "flac" if pro else "mp3_128"
        if req.quality == max_quality or req.quality == "flac" or req.quality == "mp3_320":
            if req.quality in ("flac", "mp3_320") and not pro:
                raise HTTPException(403, "Pro requis")
            if not session["audio_ready"]:
                for _ in range(60):
                    await asyncio.sleep(1)
                    if session["audio_ready"]:
                        break
                else:
                    raise HTTPException(504, "Pré-fetch audio timeout")
            output = await _get_prefetch_audio(session, session_dir, pro)
        else:
            # Lower quality audio = light ffmpeg conversion (fast, audio only)
            if not session["audio_ready"]:
                for _ in range(60):
                    await asyncio.sleep(1)
                    if session["audio_ready"]:
                        break
                else:
                    raise HTTPException(504, "Pré-fetch audio timeout")
            output = await _download_audio_direct(url, req.quality, session_dir)

    else:
        raise HTTPException(400, "Format invalide: 'video' ou 'audio'")

    if not output or not output.exists():
        raise HTTPException(500, "Téléchargement échoué")

    session["last_download"] = time.time()

    title = session["meta"].get("title", "grab")
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:80]
    filename = f"{safe_title}.{output.suffix.lstrip('.')}"

    return FileResponse(
        str(output),
        media_type="application/octet-stream",
        filename=filename,
    )


@app.get("/status/{session_id}")
async def status(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session invalide")
    return {
        "video_ready": session["video_ready"],
        "audio_ready": session["audio_ready"],
    }


# --- Pré-fetch ---

async def _fetch_meta(url: str) -> dict | None:
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--dump-json", "--no-download", url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    return json.loads(stdout)


async def _prefetch(session_id: str, url: str, pro: bool, session_dir: Path):
    video_task = asyncio.create_task(_prefetch_video(session_id, url, pro, session_dir))
    audio_task = asyncio.create_task(_prefetch_audio(session_id, url, pro, session_dir))
    await asyncio.gather(video_task, audio_task)
    asyncio.create_task(_schedule_cleanup(session_id))


async def _prefetch_video(session_id: str, url: str, pro: bool, session_dir: Path):
    if pro:
        format_sel = "bestvideo[ext=mp4]/bestvideo"
    else:
        format_sel = "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=1080]"

    output_path = str(session_dir / "video_src.%(ext)s")
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "-f", format_sel, "-o", output_path, "--no-playlist", url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if session_id in sessions:
        sessions[session_id]["video_ready"] = proc.returncode == 0


async def _prefetch_audio(session_id: str, url: str, pro: bool, session_dir: Path):
    if pro:
        format_sel = "bestaudio"
    else:
        format_sel = "bestaudio[abr<=128]/bestaudio"

    output_path = str(session_dir / "audio_src.%(ext)s")
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "-f", format_sel, "-o", output_path, "--no-playlist", url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    if session_id in sessions:
        sessions[session_id]["audio_ready"] = proc.returncode == 0


# --- Conversion ---

async def _get_prefetch_video(session: dict, session_dir: Path, pro: bool) -> Path | None:
    """Merge prefetched video + audio into a single mp4."""
    video_src = _find_file(session_dir, "video_src")
    audio_src = _find_file(session_dir, "audio_src")
    output = session_dir / f"output_max.mp4"
    if output.exists():
        return output
    # Mux video + audio together (copy, no re-encode = instant)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_src),
        "-i", str(audio_src),
        "-c", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-movflags", "+faststart",
        str(output),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return output if output.exists() else None


async def _download_video_direct(url: str, quality: str, session_dir: Path) -> Path | None:
    """Download a specific lower quality directly from source via yt-dlp."""
    heights = {"720p": 720, "480p": 480}
    h = heights.get(quality)
    if not h:
        return None

    output_path = str(session_dir / f"direct_{quality}.%(ext)s")
    format_sel = f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/best[height<={h}]"

    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "-f", format_sel,
        "--merge-output-format", "mp4",
        "-o", output_path, "--no-playlist", url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    # Find the downloaded file
    for f in session_dir.iterdir():
        if f.stem.startswith(f"direct_{quality}"):
            return f
    return None


async def _get_prefetch_audio(session: dict, session_dir: Path, pro: bool) -> Path | None:
    """Return the prefetched audio, remuxed to appropriate format."""
    source = _find_file(session_dir, "audio_src")
    # For max quality (pro: flac, free: m4a) just return source
    return source


async def _download_audio_direct(url: str, quality: str, session_dir: Path) -> Path | None:
    """Download and convert audio to the requested format via yt-dlp."""
    configs = {
        "mp3_128": {"ext": "mp3", "codec": "libmp3lame", "bitrate": "128k"},
        "m4a_128": {"ext": "m4a", "codec": "aac", "bitrate": "128k"},
    }

    cfg = configs.get(quality)
    if not cfg:
        return None

    output = session_dir / f"audio_{quality}.{cfg['ext']}"
    if output.exists():
        return output

    # Download best audio then convert
    source = _find_file(session_dir, "audio_src")
    cmd = ["ffmpeg", "-y", "-i", str(source), "-c:a", cfg["codec"]]
    if cfg["bitrate"]:
        cmd += ["-b:a", cfg["bitrate"]]
    cmd.append(str(output))

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return output if output.exists() else None


# --- Nettoyage agressif ---

async def _schedule_cleanup(session_id: str):
    """Attend 2min30 après le pré-fetch, puis vérifie si un download a eu lieu."""
    await asyncio.sleep(CLEANUP_DELAY)
    await _try_cleanup(session_id)


async def _try_cleanup(session_id: str):
    session = sessions.get(session_id)
    if not session:
        return

    now = time.time()
    last_dl = session.get("last_download")

    if last_dl:
        elapsed_since_dl = now - last_dl
        if elapsed_since_dl < CLEANUP_DELAY:
            # Re-schedule: l'user a dl récemment, on attend encore
            await asyncio.sleep(CLEANUP_DELAY - elapsed_since_dl)
            await _try_cleanup(session_id)
            return

    # Cleanup
    session_dir = Path(session["dir"])
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
    del sessions[session_id]


# Nettoyage global toutes les 60s pour les sessions zombies (>5min)
async def _global_cleanup():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        expired = [
            sid for sid, s in sessions.items()
            if now - s["created_at"] > 300  # 5min max absolue
        ]
        for sid in expired:
            session_dir = Path(sessions[sid]["dir"])
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            del sessions[sid]


@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(_global_cleanup())
    # Nettoyer les restes d'un crash précédent
    if TEMP_DIR.exists():
        for d in TEMP_DIR.iterdir():
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)


# --- Utils ---

def _find_file(session_dir: Path, prefix: str) -> Path:
    for f in session_dir.iterdir():
        if f.stem == prefix:
            return f
    raise HTTPException(500, f"Fichier source introuvable: {prefix}")

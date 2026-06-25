# Grab — Video Downloader SaaS

## Vue d'ensemble

Grab est un service de téléchargement de vidéos/audio depuis YouTube, TikTok, Instagram, Twitter et Reddit. Design propre sans pub, monétisé par un abonnement Pro. Alternative à notube/y2mate avec une UX soignée.

**Statut** : Mockup fonctionnel (Docker tourne en local). Pas encore d'auth réelle ni de paiement intégré.

**Emplacement** : `~/Projets/video-downloader/`

---

## Stack technique

| Couche | Techno |
|--------|--------|
| Frontend | HTML/CSS/JS vanilla (Space Grotesk + Inter, dark/light mode) |
| Backend | Python FastAPI + yt-dlp + ffmpeg |
| Déploiement | Docker Compose (backend Python + nginx pour le frontend statique) |

---

## Structure des fichiers

```
video-downloader/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
└── frontend/
    ├── index.html        # Page principale (input URL + résultats)
    ├── pro.html          # Page pricing Pro
    ├── api.html          # Documentation API
    └── account.html      # Login/signup + gestion compte
```

---

## Architecture backend

### Endpoints

| Route | Méthode | Rôle |
|-------|---------|------|
| `/prepare` | POST | Reçoit une URL, retourne les métadonnées (titre, thumbnail, durée, vues) + lance le pré-fetch en background (vidéo max + audio max en parallèle) |
| `/status/{session_id}` | GET | Poll la readiness du pré-fetch (video_ready, audio_ready) |
| `/download` | POST | Qualité max = sert le fichier pré-fetché (instant). Qualité inférieure = yt-dlp direct ou conversion ffmpeg légère |

### Flow

1. L'utilisateur colle une URL → auto-detect plateforme + `POST /prepare`
2. Le backend fetch les métadonnées via `yt-dlp --dump-json`
3. En parallèle, pré-fetch de la meilleure vidéo ET du meilleur audio (séparés)
4. Le frontend poll `/status/{session_id}` toutes les 1.5s
5. L'utilisateur choisit un format → `POST /download`
   - Si qualité max : mux vidéo+audio via `ffmpeg -c copy` (pas de re-encode, quasi instantané)
   - Si qualité inférieure : yt-dlp re-download à la bonne résolution ou conversion ffmpeg

### Nettoyage

- 2min30 après le dernier download → suppression des fichiers de la session
- 5min max absolue → suppression forcée (sweep global toutes les 60s)
- Au démarrage : nettoie les restes d'un crash précédent

### Sessions

Stockées en mémoire (dict Python). Pas de base de données. Chaque session contient :
- `dir` : chemin du dossier temporaire (`/tmp/grab/{session_id}`)
- `meta` : métadonnées yt-dlp complètes
- `url`, `pro` (booléen)
- `video_ready`, `audio_ready` (booléens)
- `created_at`, `last_download` (timestamps)

---

## Modèle freemium

| | Free | Pro (4€/mois) |
|---|---|---|
| Vidéo | Jusqu'à 1080p MP4 | Jusqu'à 4K MP4 |
| Audio | MP3 128kbps, M4A 128kbps | FLAC, MP3 320kbps |
| Quota | 5 grabs/jour | Illimité |
| Priorité | Standard | Prioritaire |
| API | 50 req/jour | 1000 req/jour |

---

## Frontend

### Page principale (`index.html`)

- Champ URL unique avec détection automatique de la plateforme
- Glow coloré qui change selon la plateforme détectée :
  - YouTube → rouge `#ff2d2d`
  - TikTok → cyan `#00f2ea`
  - Instagram → violet `#c13584`
  - Twitter/X → bleu `#1d9bf0`
  - Reddit → orange `#ff4500`
- Icône SVG de la plateforme avec animation spin-in/spin-out au changement
- Auto-prefetch au paste (pas besoin d'appuyer Entrée), debounce 500ms
- Résultats : card avec thumbnail + titre + durée + vues
- Boutons de format séparés Vidéo / Audio
- Progress bar en 2 phases :
  1. "Conversion" (barre indéterminée animée)
  2. "Transfert" (progression réelle avec vitesse + ETA)
- Barre de quota journalier (2/5 grabs)
- Badge "Pro" en exposant sur le titre "Grab"
- Dark/light mode toggle (persiste en localStorage)

### Page Pro (`pro.html`)

- Liste des avantages (checklist avec cercles oranges)
- Prix affiché : 4€/mois
- CTA "Passer Pro" avec gradient orange
- Mention "Sans engagement · Remboursé sous 7 jours"

### Page API (`api.html`)

- Base URL : `https://api.grab.download/v1`
- Auth par header `Authorization: Bearer grab_sk_xxxxxxxxxxxx`
- Documentation des 3 endpoints avec exemples de requête/réponse
- Exemple complet en curl (prepare → poll status → download)
- Limites : 50 req/jour (Free), 1000 req/jour (Pro)

### Page Compte (`account.html`)

- Formulaires login/signup avec tabs
- OAuth Google + GitHub
- Affichage du token API (avec bouton copier)
- Bouton déconnexion

---

## Design system

| Propriété | Dark | Light |
|-----------|------|-------|
| `--bg` | `#0a0a0f` | `#f4f4f8` |
| `--surface` | `#14141f` | `#ffffff` |
| `--surface-hover` | `#1c1c2a` | `#eeeef2` |
| `--border` | `#2a2a3a` | `#d8d8e0` |
| `--text` | `#e8e8f0` | `#1a1a2e` |
| `--text-muted` | `#6b6b80` | `#6b6b80` |
| `--accent` | `#6366f1` (indigo) | idem |
| `--radius` | `12px` | idem |

Typographies :
- Titres/marque : Space Grotesk (700)
- Corps : Inter (400, 500)
- Code : JetBrains Mono (page API)

---

## Docker Compose

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    restart: unless-stopped

  frontend:
    image: nginx:alpine
    ports:
      - "3000:80"
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
    restart: unless-stopped
```

Le Dockerfile backend :
- Base : `python:3.12-slim`
- Installe ffmpeg via apt + yt-dlp via pip
- Lance uvicorn sur le port 8000

---

## Dépendances backend

```
fastapi
uvicorn[standard]
yt-dlp
pydantic
```

---

## Ce qui reste à faire

- [ ] Auth réelle (JWT, sessions persistantes, OAuth Google/GitHub fonctionnel)
- [ ] Paiement Stripe pour le plan Pro
- [ ] Rate limiting réel (actuellement pas implémenté côté serveur)
- [ ] Base de données pour les comptes utilisateur
- [ ] Stockage persistant des sessions (Redis ou similaire) au lieu du dict en mémoire
- [ ] Déploiement en production (domaine, HTTPS, Cloudflare)
- [ ] Gestion des erreurs yt-dlp plus fine (vidéo privée, géobloquée, etc.)
- [ ] Tests

---

## Code source complet

### `backend/main.py`

```python
import asyncio
import subprocess
import json
import uuid
import time
import os
import shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


class PrepareRequest(BaseModel):
    url: str
    pro: bool = False


class ConvertRequest(BaseModel):
    session_id: str
    format: str  # "video" ou "audio"
    quality: str  # "4k", "1080p", "720p", "480p", "flac", "mp3_320", "mp3_128", "m4a_128"


@app.post("/prepare")
async def prepare(req: PrepareRequest):
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
        "pro": req.pro,
        "video_ready": False,
        "audio_ready": False,
        "created_at": time.time(),
        "last_download": None,
    }

    asyncio.create_task(_prefetch(session_id, req.url, req.pro, session_dir))

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
            output = await _download_video_direct(url, req.quality, session_dir)

    elif req.format == "audio":
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

    for f in session_dir.iterdir():
        if f.stem.startswith(f"direct_{quality}"):
            return f
    return None


async def _get_prefetch_audio(session: dict, session_dir: Path, pro: bool) -> Path | None:
    """Return the prefetched audio, remuxed to appropriate format."""
    source = _find_file(session_dir, "audio_src")
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
            await asyncio.sleep(CLEANUP_DELAY - elapsed_since_dl)
            await _try_cleanup(session_id)
            return

    session_dir = Path(session["dir"])
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
    del sessions[session_id]


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
    asyncio.create_task(_global_cleanup())
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
```

---

## Lancer le projet

```bash
cd ~/Projets/video-downloader
docker compose up --build
```

- Frontend : http://localhost:3000
- Backend API : http://localhost:8000

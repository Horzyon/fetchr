import aiosqlite
import secrets
from pathlib import Path
from datetime import datetime

DB_PATH = Path("/data/fetchr.db")


def _generate_api_token() -> str:
    return "fetchr_sk_" + secrets.token_hex(16)


async def init_db():
    """Create the database and users table if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_pro INTEGER DEFAULT 0,
                pro_expires_at TEXT,
                api_token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def create_user(email: str, username: str, password_hash: str) -> dict:
    """Insert a new user and return the user dict."""
    api_token = _generate_api_token()
    created_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            INSERT INTO users (email, username, password_hash, api_token, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email, username, password_hash, api_token, created_at),
        )
        await db.commit()
        user_id = cursor.lastrowid

    return {
        "id": user_id,
        "email": email,
        "username": username,
        "is_pro": False,
        "api_token": api_token,
    }


async def get_user_by_email(email: str) -> dict | None:
    """Fetch a user by email. Returns full row as dict or None."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)


async def get_user_by_id(user_id: int) -> dict | None:
    """Fetch a user by id. Returns full row as dict or None."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

"""
ระบบ Login / Register และการเก็บประวัติแชทแบบถาวรของ Solar Chat
ใช้ SQLite เก็บผู้ใช้ เซสชันแชท และข้อความ + JWT สำหรับยืนยันตัวตน
"""
import os
import sqlite3
import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from fastapi import Header, HTTPException

DB_PATH = os.getenv("AUTH_DB_PATH", "app.db")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-please-in-.env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """สร้างตารางถ้ายังไม่มี (เรียกครั้งเดียวตอน backend เริ่มทำงาน)"""
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'แชทใหม่',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        """
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# รหัสผ่านและ JWT
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: int, username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="โทเคนไม่ถูกต้อง")


def get_current_user(authorization: str = Header(default=None)) -> dict:
    """FastAPI dependency: ดึงผู้ใช้ปัจจุบันจาก header Authorization: Bearer <token>"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อนใช้งาน")
    token = authorization.removeprefix("Bearer ").strip()
    payload = decode_access_token(token)
    return {"id": int(payload["sub"]), "username": payload["username"]}


# ---------------------------------------------------------------------------
# ผู้ใช้ (register / login)
# ---------------------------------------------------------------------------

def create_user(username: str, password: str) -> dict:
    username = username.strip()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้ต้องมีอย่างน้อย 3 ตัวอักษร")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="มีชื่อผู้ใช้นี้อยู่แล้ว กรุณาเลือกชื่ออื่น")

        password_hash = hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, password_hash, now),
        )
        conn.commit()
        return {"id": cur.lastrowid, "username": username}
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> dict:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
        return {"id": row["id"], "username": row["username"]}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# เซสชันแชทและข้อความ (ประวัติแชทถาวรผูกกับผู้ใช้)
# ---------------------------------------------------------------------------

def ensure_session(user_id: int, session_id: str, title: str = "แชทใหม่") -> None:
    """สร้างเซสชันถ้ายังไม่มี (ไม่ทับของเดิมถ้ามีอยู่แล้ว)"""
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO sessions (id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, title, now, now),
    )
    conn.commit()
    conn.close()


def touch_session(session_id: str, title: str | None = None) -> None:
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    if title:
        conn.execute("UPDATE sessions SET updated_at = ?, title = ? WHERE id = ?", (now, title, session_id))
    else:
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
    conn.commit()
    conn.close()


def session_belongs_to_user(session_id: str, user_id: int) -> bool:
    conn = get_db()
    row = conn.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return bool(row) and row["user_id"] == user_id


def list_sessions(user_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_messages(session_id: str) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_message(session_id: str, role: str, content: str) -> None:
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    conn.commit()
    conn.close()


def clear_session_messages(session_id: str) -> None:
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute(
        "UPDATE sessions SET title = 'แชทใหม่', updated_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), session_id),
    )
    conn.commit()
    conn.close()


def delete_session(session_id: str) -> None:
    conn = get_db()
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

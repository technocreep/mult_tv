import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from config import SESSION_MAX_AGE_DAYS
from db import get_db
from auth import (
    check_rate_limit, record_failed_login, clear_rate_limit,
    hash_password, verify_password, get_current_user
)
from models import LoginRequest

router = APIRouter(prefix="/api")


@router.post("/login")
async def login(data: LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(ip)

    conn = get_db()
    row = conn.execute(
        'SELECT id, username, password_hash, salt, role FROM users WHERE username = ?',
        (data.username,)
    ).fetchone()

    if not row or not verify_password(data.password, row["password_hash"], row["salt"]):
        conn.close()
        record_failed_login(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    clear_rate_limit(ip)

    # Миграция старого SHA-256 хеша на bcrypt при успешном логине
    if not row["password_hash"].startswith("$2b$") and not row["password_hash"].startswith("$2a$"):
        new_hash = hash_password(data.password)
        conn.execute('UPDATE users SET password_hash = ?, salt = ? WHERE id = ?', (new_hash, "", row["id"]))

    # Очистка старых сессий
    conn.execute('DELETE FROM sessions WHERE created_at < ?',
                 (datetime.now() - timedelta(days=SESSION_MAX_AGE_DAYS),))

    token = secrets.token_hex(32)
    conn.execute('INSERT INTO sessions (token, user_id) VALUES (?, ?)', (token, row["id"]))
    conn.commit()
    conn.close()

    response = JSONResponse({"username": row["username"], "role": row["role"]})
    response.set_cookie("session_token", token, httponly=True, samesite="strict", max_age=SESSION_MAX_AGE_DAYS*24*3600)
    return response


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        conn = get_db()
        conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
        conn.commit()
        conn.close()
    response = JSONResponse({"ok": True})
    response.delete_cookie("session_token")
    return response


@router.get("/me")
async def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    return user

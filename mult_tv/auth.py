import time
import bcrypt
import hashlib
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from config import SESSION_MAX_AGE_DAYS

# --- Rate limiter ---

login_attempts = {}  # IP -> (count, first_attempt_time)
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 300  # 5 минут


def check_rate_limit(ip: str):
    now = time.time()
    if ip in login_attempts:
        count, first_time = login_attempts[ip]
        if now - first_time > RATE_LIMIT_WINDOW:
            del login_attempts[ip]
        elif count >= RATE_LIMIT_MAX:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")


def record_failed_login(ip: str):
    now = time.time()
    if ip in login_attempts:
        count, first_time = login_attempts[ip]
        if now - first_time > RATE_LIMIT_WINDOW:
            login_attempts[ip] = (1, now)
        else:
            login_attempts[ip] = (count + 1, first_time)
    else:
        login_attempts[ip] = (1, now)


def clear_rate_limit(ip: str):
    login_attempts.pop(ip, None)


# --- Утилиты для паролей ---

def hash_password(password: str):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, stored_hash: str, salt: str = ""):
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"):
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    # Fallback для старых SHA-256 хешей (миграция)
    check = hashlib.sha256((salt + password).encode()).hexdigest()
    return check == stored_hash


# --- Auth хелперы ---

def get_current_user(request: Request):
    from db import get_db
    token = request.cookies.get("session_token")
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        '''SELECT u.id, u.username, u.role, s.created_at as session_created
           FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ?''',
        (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    # Session expiry check
    try:
        created = datetime.fromisoformat(row["session_created"])
        if datetime.now() - created > timedelta(days=SESSION_MAX_AGE_DAYS):
            conn = get_db()
            conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
            conn.commit()
            conn.close()
            return None
    except (ValueError, TypeError):
        pass
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(request: Request):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

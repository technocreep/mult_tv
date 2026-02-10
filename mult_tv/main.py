import os
import random
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

VIDEO_DIR = "/downloads"
DB_PATH = "/app/data/history.db"
STATIC_DIR = "/app/static"

# --- Pydantic модели ---

class LoginRequest(BaseModel):
    username: str
    password: str

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"

class ChangePasswordRequest(BaseModel):
    password: str

class MarkWatchedRequest(BaseModel):
    file_path: str

class PlayRequest(BaseModel):
    path: str

# --- Утилиты для паролей ---

def hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return password_hash, salt

def verify_password(password: str, password_hash: str, salt: str):
    check_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return check_hash == password_hash

# --- Инициализация БД ---

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT,
            watched_at TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Создаём дефолтного админа если нет ни одного пользователя
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        pw_hash, salt = hash_password("admin")
        cursor.execute(
            'INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)',
            ("admin", pw_hash, salt, "admin")
        )

    conn.commit()
    conn.close()

init_db()

# --- Auth хелперы ---

def get_current_user(request: Request):
    token = request.cookies.get("session_token")
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        'SELECT u.id, u.username, u.role FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ?',
        (token,)
    ).fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None

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

# --- Публичные эндпоинты ---

@app.post("/api/login")
async def login(data: LoginRequest, response: Response):
    conn = get_db()
    row = conn.execute(
        'SELECT id, username, password_hash, salt, role FROM users WHERE username = ?',
        (data.username,)
    ).fetchone()

    if not row or not verify_password(data.password, row["password_hash"], row["salt"]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = secrets.token_hex(32)
    conn.execute('INSERT INTO sessions (token, user_id) VALUES (?, ?)', (token, row["id"]))
    conn.commit()
    conn.close()

    response = JSONResponse({"username": row["username"], "role": row["role"]})
    response.set_cookie("session_token", token, httponly=True, samesite="strict", max_age=30*24*3600)
    return response

@app.post("/api/logout")
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

@app.get("/api/me")
async def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401)
    return user

# --- Защищённые эндпоинты ---

def get_top_folder(file_path):
    """Возвращает имя папки верхнего уровня относительно VIDEO_DIR."""
    rel = os.path.relpath(file_path, VIDEO_DIR)
    parts = rel.split(os.sep)
    return parts[0] if len(parts) > 1 else ""

@app.get("/api/get_random")
async def get_random_video(request: Request, current_path: str = ""):
    require_auth(request)

    conn = get_db()
    cursor = conn.cursor()

    ten_days_ago = datetime.now() - timedelta(days=10)
    cursor.execute('SELECT file_path FROM history WHERE watched_at > ?', (ten_days_ago,))
    recently_watched = [row[0] for row in cursor.fetchall()]

    all_files = []
    for root, dirs, files in os.walk(VIDEO_DIR):
        for file in files:
            if file.lower().endswith('.mp4'):
                all_files.append(os.path.join(root, file))

    available_files = [f for f in all_files if f not in recently_watched]

    if not available_files:
        available_files = all_files if all_files else []

    if not available_files:
        conn.close()
        return {"error": "Папка загрузок пуста"}

    # Исключаем файлы из текущей папки (переключаем шоу)
    if current_path:
        current_folder = get_top_folder(current_path)
        other_folder_files = [f for f in available_files if get_top_folder(f) != current_folder]
        if other_folder_files:
            available_files = other_folder_files

    chosen_video = random.choice(available_files)
    conn.close()

    rel_path = os.path.relpath(chosen_video, VIDEO_DIR)
    return {
        "title": os.path.basename(chosen_video),
        "url": f"/stream/{rel_path}",
        "file_path": chosen_video
    }

@app.get("/stream/{file_path:path}")
async def stream_video(file_path: str, request: Request):
    require_auth(request)
    full_path = os.path.join(VIDEO_DIR, file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404)
    return FileResponse(full_path)

@app.post("/api/mark_watched")
async def mark_watched(data: MarkWatchedRequest, request: Request):
    require_auth(request)
    conn = get_db()
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = conn.execute(
        'SELECT id FROM history WHERE file_path = ? AND watched_at > ?',
        (data.file_path, today_start)
    ).fetchone()
    if not existing:
        conn.execute('INSERT INTO history (file_path, watched_at) VALUES (?, ?)',
                     (data.file_path, datetime.now()))
        conn.commit()
    conn.close()
    return {"ok": True}

# --- Админские эндпоинты ---

@app.get("/api/admin/users")
async def list_users(request: Request):
    require_admin(request)
    conn = get_db()
    rows = conn.execute('SELECT id, username, role, created_at FROM users ORDER BY id').fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/admin/users")
async def create_user(data: CreateUserRequest, request: Request):
    require_admin(request)
    if data.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
    pw_hash, salt = hash_password(data.password)
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)',
            (data.username, pw_hash, salt, data.role)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Username already exists")
    conn.close()
    return {"ok": True}

@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: int, request: Request):
    admin = require_admin(request)
    if admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    conn = get_db()
    conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/admin/users/{user_id}/password")
async def change_user_password(user_id: int, data: ChangePasswordRequest, request: Request):
    require_admin(request)
    pw_hash, salt = hash_password(data.password)
    conn = get_db()
    conn.execute('UPDATE users SET password_hash = ?, salt = ? WHERE id = ?', (pw_hash, salt, user_id))
    conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/admin/stats")
async def get_stats(request: Request):
    require_admin(request)
    conn = get_db()

    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_views = conn.execute('SELECT COUNT(*) FROM history').fetchone()[0]

    total_videos = 0
    for root, dirs, files in os.walk(VIDEO_DIR):
        for file in files:
            if file.lower().endswith('.mp4'):
                total_videos += 1

    conn.close()
    return {"total_users": total_users, "total_views": total_views, "total_videos": total_videos}

@app.delete("/api/admin/history")
async def reset_history(request: Request):
    require_admin(request)
    conn = get_db()
    conn.execute('DELETE FROM history')
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/admin/videos/{file_path:path}")
async def delete_video(file_path: str, request: Request):
    require_admin(request)
    full_path = os.path.join(VIDEO_DIR, file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404)
    os.remove(full_path)
    return {"ok": True}

@app.get("/api/admin/browse")
async def browse_files(request: Request, path: str = ""):
    require_admin(request)
    full_path = os.path.realpath(os.path.join(VIDEO_DIR, path))
    if not full_path.startswith(os.path.realpath(VIDEO_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isdir(full_path):
        raise HTTPException(status_code=404, detail="Directory not found")

    folders = []
    files = []
    for entry in sorted(os.listdir(full_path)):
        if entry.startswith('.'):
            continue
        entry_path = os.path.join(full_path, entry)
        if os.path.isdir(entry_path):
            folders.append(entry)
        elif entry.lower().endswith('.mp4'):
            rel = os.path.relpath(entry_path, VIDEO_DIR)
            size_mb = round(os.path.getsize(entry_path) / (1024 * 1024), 1)
            files.append({"name": entry, "path": rel, "size_mb": size_mb})

    return {"current_path": path, "folders": folders, "files": files}

@app.post("/api/admin/play")
async def play_video(data: PlayRequest, request: Request):
    require_admin(request)
    full_path = os.path.realpath(os.path.join(VIDEO_DIR, data.path))
    if not full_path.startswith(os.path.realpath(VIDEO_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full_path) or not data.path.lower().endswith('.mp4'):
        raise HTTPException(status_code=404, detail="Video not found")

    return {
        "title": os.path.basename(full_path),
        "url": f"/stream/{data.path}",
        "file_path": data.path
    }

@app.get("/api/admin/videos")
async def list_videos(request: Request):
    require_admin(request)
    videos = []
    for root, dirs, files in os.walk(VIDEO_DIR):
        for file in files:
            if file.lower().endswith('.mp4'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, VIDEO_DIR)
                size_mb = round(os.path.getsize(full_path) / (1024 * 1024), 1)
                videos.append({"name": file, "path": rel_path, "size_mb": size_mb})
    return videos

# --- Страницы ---

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

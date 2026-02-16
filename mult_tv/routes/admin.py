import os
import sqlite3
from fastapi import APIRouter, HTTPException, Request
from config import VIDEO_DIR
from db import get_db
from auth import require_admin, hash_password
from video import safe_path
from models import CreateUserRequest, ChangePasswordRequest, PlayRequest

router = APIRouter(prefix="/api/admin")


@router.get("/users")
async def list_users(request: Request):
    require_admin(request)
    conn = get_db()
    rows = conn.execute('SELECT id, username, role, created_at FROM users ORDER BY id').fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.post("/users")
async def create_user(data: CreateUserRequest, request: Request):
    require_admin(request)
    if data.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'")
    pw_hash = hash_password(data.password)
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)',
            (data.username, pw_hash, "", data.role)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Username already exists")
    conn.close()
    return {"ok": True}


@router.delete("/users/{user_id}")
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


@router.put("/users/{user_id}/password")
async def change_user_password(user_id: int, data: ChangePasswordRequest, request: Request):
    require_admin(request)
    pw_hash = hash_password(data.password)
    conn = get_db()
    conn.execute('UPDATE users SET password_hash = ?, salt = ? WHERE id = ?', (pw_hash, "", user_id))
    conn.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/stats")
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


@router.delete("/history")
async def reset_history(request: Request):
    require_admin(request)
    conn = get_db()
    conn.execute('DELETE FROM history')
    conn.commit()
    conn.close()
    return {"ok": True}


@router.delete("/videos/{file_path:path}")
async def delete_video(file_path: str, request: Request):
    require_admin(request)
    full_path = safe_path(VIDEO_DIR, file_path)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404)
    os.remove(full_path)
    return {"ok": True}


@router.get("/browse")
async def browse_files(request: Request, path: str = ""):
    require_admin(request)
    full_path = safe_path(VIDEO_DIR, path)
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


@router.post("/play")
async def play_video(data: PlayRequest, request: Request):
    require_admin(request)
    full_path = safe_path(VIDEO_DIR, data.path)
    if not os.path.isfile(full_path) or not data.path.lower().endswith('.mp4'):
        raise HTTPException(status_code=404, detail="Video not found")

    return {
        "title": os.path.basename(full_path),
        "url": f"/stream/{data.path}",
        "file_path": data.path
    }


@router.get("/videos")
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


@router.get("/reports")
async def list_reports(request: Request):
    require_admin(request)
    conn = get_db()
    rows = conn.execute('''
        SELECT r.id, r.file_path, r.comment, r.created_at, u.username
        FROM reports r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC
    ''').fetchall()
    conn.close()
    return [dict(row) for row in rows]


@router.delete("/reports/{report_id}")
async def delete_report(report_id: int, request: Request):
    require_admin(request)
    conn = get_db()
    conn.execute('DELETE FROM reports WHERE id = ?', (report_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

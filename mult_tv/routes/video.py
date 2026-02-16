import os
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from config import VIDEO_DIR
from db import get_db
from auth import require_auth
from video import safe_path, get_show_name, get_all_videos, get_sorted_shows, pick_from_show
from models import MarkWatchedRequest, ReportRequest

router = APIRouter()


@router.get("/api/shows")
async def list_shows(request: Request):
    require_auth(request)
    return get_sorted_shows()


@router.get("/api/get_random")
async def get_random_video(request: Request, current_path: str = "", same_folder: bool = False, show: str = ""):
    require_auth(request)

    conn = get_db()
    cursor = conn.cursor()

    ten_days_ago = datetime.now() - timedelta(days=10)
    cursor.execute('SELECT file_path FROM history WHERE watched_at > ?', (ten_days_ago,))
    recently_watched = [row[0] for row in cursor.fetchall()]

    all_files = get_all_videos()

    if not all_files:
        conn.close()
        return {"error": "Папка загрузок пуста"}

    chosen_video = None

    if show:
        chosen_video = pick_from_show(show, all_files, recently_watched)
    elif current_path and same_folder:
        current_show = get_show_name(os.path.join(VIDEO_DIR, current_path))
        chosen_video = pick_from_show(current_show, all_files, recently_watched)
    elif current_path:
        current_show = get_show_name(os.path.join(VIDEO_DIR, current_path))
        shows = get_sorted_shows()
        if shows:
            try:
                idx = shows.index(current_show)
                next_show = shows[(idx + 1) % len(shows)]
            except ValueError:
                next_show = shows[0]
            chosen_video = pick_from_show(next_show, all_files, recently_watched)

    if not chosen_video:
        available = [f for f in all_files if f not in recently_watched]
        if not available:
            available = all_files
        chosen_video = random.choice(available)

    conn.close()

    rel_path = os.path.relpath(chosen_video, VIDEO_DIR)
    return {
        "title": os.path.basename(chosen_video),
        "url": f"/stream/{rel_path}",
        "file_path": rel_path,
        "show": get_show_name(chosen_video)
    }


@router.get("/stream/{file_path:path}")
async def stream_video(file_path: str, request: Request):
    require_auth(request)
    full_path = safe_path(VIDEO_DIR, file_path)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404)
    return FileResponse(full_path)


@router.post("/api/mark_watched")
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


@router.post("/api/report")
async def create_report(data: ReportRequest, request: Request):
    user = require_auth(request)
    conn = get_db()
    conn.execute(
        'INSERT INTO reports (user_id, file_path, comment, created_at) VALUES (?, ?, ?, ?)',
        (user["id"], data.file_path, data.comment, datetime.now())
    )
    conn.commit()
    conn.close()
    return {"ok": True}

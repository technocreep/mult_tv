import os
import random
import sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

VIDEO_DIR = "/downloads"
DB_PATH = "/app/data/history.db"
STATIC_DIR = "/app/static"

# Инициализация БД
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT,
            watched_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.get("/api/get_random")
async def get_random_video():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Исключаем то, что смотрели последние 10 дней
    ten_days_ago = datetime.now() - timedelta(days=10)
    cursor.execute('SELECT file_path FROM history WHERE watched_at > ?', (ten_days_ago,))
    recently_watched = [row[0] for row in cursor.fetchall()]
    
    all_files = []
    for root, dirs, files in os.walk(VIDEO_DIR):
        for file in files:
            if file.lower().endswith('.mp4'):
                all_files.append(os.path.join(root, file))
    
    available_files = [f for f in all_files if f not in recently_watched]
    
    # Если всё пересмотрено, сбрасываем фильтр (кроме совсем последних)
    if not available_files:
        available_files = all_files if all_files else []

    if not available_files:
        return {"error": "Папка загрузок пуста"}

    chosen_video = random.choice(available_files)
    
    cursor.execute('INSERT INTO history (file_path, watched_at) VALUES (?, ?)',
                   (chosen_video, datetime.now()))
    conn.commit()
    conn.close()

    rel_path = os.path.relpath(chosen_video, VIDEO_DIR)
    return {
        "title": os.path.basename(chosen_video),
        "url": f"/stream/{rel_path}"
    }

@app.get("/stream/{file_path:path}")
async def stream_video(file_path: str):
    full_path = os.path.join(VIDEO_DIR, file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404)
    # FileResponse автоматически поддерживает Range Requests для перемотки и стриминга
    return FileResponse(full_path)

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

# Подключаем статику (если будут картинки/футажи)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
import os
import json
import random
import subprocess
from fastapi import HTTPException
from config import VIDEO_DIR, COMPLETE_DIR


def safe_path(base_dir: str, user_path: str):
    full = os.path.realpath(os.path.join(base_dir, user_path))
    if not full.startswith(os.path.realpath(base_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    return full


def get_show_name(file_path):
    """Возвращает имя папки-сериала относительно VIDEO_DIR.
    Пропускает промежуточные папки complete/incomplete."""
    rel = os.path.relpath(file_path, VIDEO_DIR)
    parts = rel.split(os.sep)
    if len(parts) > 2 and parts[0] in ('complete', 'incomplete'):
        return parts[1]
    return parts[0] if len(parts) > 1 else ""


def get_blocked_files():
    """Возвращает set файлов, не прошедших проверку."""
    from db import get_db
    conn = get_db()
    rows = conn.execute('SELECT file_path FROM video_checks WHERE ok = 0').fetchall()
    conn.close()
    return {row[0] for row in rows}


def get_all_videos():
    """Собирает все mp4-файлы из VIDEO_DIR, исключая заблокированные."""
    blocked = get_blocked_files()
    files = []
    for root, dirs, filenames in os.walk(VIDEO_DIR):
        for f in filenames:
            if f.lower().endswith('.mp4'):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, VIDEO_DIR)
                if rel_path not in blocked:
                    files.append(full_path)
    return files


def get_all_videos_unfiltered():
    """Собирает все mp4-файлы из VIDEO_DIR без фильтрации."""
    files = []
    for root, dirs, filenames in os.walk(VIDEO_DIR):
        for f in filenames:
            if f.lower().endswith('.mp4'):
                files.append(os.path.join(root, f))
    return files


def get_sorted_shows():
    """Возвращает отсортированный список папок-сериалов из complete/."""
    if not os.path.isdir(COMPLETE_DIR):
        return []
    return sorted([
        d for d in os.listdir(COMPLETE_DIR)
        if os.path.isdir(os.path.join(COMPLETE_DIR, d)) and not d.startswith('.')
    ])


def pick_from_show(show_name, all_files, recently_watched):
    """Выбирает случайную непросмотренную серию из указанного сериала."""
    show_files = [f for f in all_files if get_show_name(f) == show_name]
    if not show_files:
        return None
    available = [f for f in show_files if f not in recently_watched]
    if not available:
        available = show_files
    return random.choice(available)


def validate_video(file_path):
    """Проверяет видеофайл через ffprobe. Возвращает dict с результатом."""
    result = {
        "ok": True,
        "errors": [],
        "video_codec": "",
        "audio_codec": "",
        "duration": 0,
        "size_mb": 0,
    }

    # Проверка размера
    try:
        size = os.path.getsize(file_path)
        result["size_mb"] = round(size / (1024 * 1024), 1)
        if size == 0:
            result["ok"] = False
            result["errors"].append("Файл пустой (0 байт)")
            return result
    except OSError:
        result["ok"] = False
        result["errors"].append("Файл не найден или недоступен")
        return result

    # Запуск ffprobe
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_streams", "-show_format",
                "-of", "json", file_path
            ],
            capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        result["ok"] = False
        result["errors"].append("Таймаут ffprobe (30с)")
        return result
    except FileNotFoundError:
        result["ok"] = False
        result["errors"].append("ffprobe не установлен")
        return result

    if proc.returncode != 0:
        result["ok"] = False
        error_msg = proc.stderr.strip()[:200] if proc.stderr else "ffprobe error"
        result["errors"].append(f"ffprobe ошибка: {error_msg}")
        return result

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        result["ok"] = False
        result["errors"].append("Не удалось разобрать вывод ffprobe")
        return result

    streams = data.get("streams", [])
    fmt = data.get("format", {})

    # Проверка видеопотока
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    if not video_streams:
        result["ok"] = False
        result["errors"].append("Нет видеопотока")
    else:
        vcodec = video_streams[0].get("codec_name", "unknown")
        result["video_codec"] = vcodec
        if vcodec not in ("h264", "hevc", "vp9", "av1"):
            result["ok"] = False
            result["errors"].append(f"Неподдерживаемый видеокодек: {vcodec}")

    # Проверка аудиопотока
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not audio_streams:
        result["ok"] = False
        result["errors"].append("Нет аудиопотока")
    else:
        acodec = audio_streams[0].get("codec_name", "unknown")
        result["audio_codec"] = acodec
        if acodec not in ("aac", "mp3", "opus", "vorbis", "flac"):
            result["ok"] = False
            result["errors"].append(f"Неподдерживаемый аудиокодек: {acodec}")

    # Проверка длительности
    try:
        duration = float(fmt.get("duration", 0))
        result["duration"] = round(duration, 1)
        if duration <= 0:
            result["ok"] = False
            result["errors"].append("Длительность = 0")
    except (ValueError, TypeError):
        result["ok"] = False
        result["errors"].append("Не удалось определить длительность")

    return result

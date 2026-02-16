import os
import random
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


def get_all_videos():
    """Собирает все mp4-файлы из VIDEO_DIR."""
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

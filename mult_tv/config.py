import os

VIDEO_DIR = "/downloads"
DB_PATH = "/app/data/history.db"
STATIC_DIR = "/app/static"
SESSION_MAX_AGE_DAYS = 30
COMPLETE_DIR = os.path.join(VIDEO_DIR, "complete")
TRANSMISSION_URL = "http://transmission:9091"
TRANSMISSION_USER = os.environ.get("TRANSMISSION_USER", "admin")
TRANSMISSION_PASS = os.environ.get("TRANSMISSION_PASS", "")

from dotenv import load_dotenv
import os

# Загружаем .env
load_dotenv()

# ======================
# SECURITY
# ======================
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY не задан в переменных окружения")

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

# ======================
# ALLOWED_HOSTS
# ======================
_raw_allowed_hosts = os.getenv("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _raw_allowed_hosts.split(",") if h.strip()]

# DEV fallback (ngrok, local)
if DEBUG:
    if not ALLOWED_HOSTS:
        ALLOWED_HOSTS = ["*"]
    else:
        ALLOWED_HOSTS += [
            ".ngrok-free.dev",
            ".ngrok-free.app",
            "localhost",
            "127.0.0.1",
        ]

# ======================
# CSRF
# ======================
_raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _raw_csrf.split(",") if o.strip()]

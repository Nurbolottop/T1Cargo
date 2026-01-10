from dotenv import load_dotenv
import os

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise Exception("SECRET_KEY не задан в переменных окружения")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

_raw_allowed_hosts = os.getenv('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [h.strip() for h in _raw_allowed_hosts.split(',') if h.strip()]

if DEBUG:
    # удобный dev-режим для теста Telegram WebApp через ngrok
    if not ALLOWED_HOSTS:
        ALLOWED_HOSTS = ['*']
    else:
        ALLOWED_HOSTS.extend(['.ngrok-free.dev', '.ngrok-free.app'])
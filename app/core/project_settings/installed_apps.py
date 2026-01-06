from dotenv import load_dotenv
import os

load_dotenv()

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

#ckeditor
    'ckeditor',
    'ckeditor_uploader',
    'django_resized',
#apps
    'apps.base',
    'apps.telegram_bot',
    'apps.contacts',
]
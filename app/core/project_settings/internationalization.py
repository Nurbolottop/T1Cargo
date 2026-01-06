from dotenv import load_dotenv
import os

load_dotenv()

LANGUAGE_CODE = os.getenv('LANGUAGE_CODE', 'ru')

TIME_ZONE = os.getenv('TIME_ZONE', 'Asia/Bishkek')

USE_I18N = True

USE_TZ = True
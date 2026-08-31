import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# En una instalación nativa (sin Docker) nadie inyecta las variables de entorno,
# así que se leen del .env. Se busca primero junto a manage.py y luego en la raíz
# del repositorio. Lo que ya venga en el entorno real tiene prioridad: por eso
# override=False, y así `DB_ENGINE=sqlite python manage.py test` sigue mandando.
for candidate in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
    if candidate.is_file():
        load_dotenv(candidate, override=False)
        break

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-prototype-only-key")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    # "daphne" va primero a propósito: en Channels 4 es esta app la que reemplaza
    # `runserver` por un servidor ASGI. Sin ella —o puesta después de
    # django.contrib.staticfiles, que también lo reemplaza— `manage.py runserver`
    # sirve HTTP con el servidor WSGI de Django y responde 404 a /ws/..., así que
    # el contador de estudiantes en vivo y las órdenes del Master no funcionan,
    # sin ningún mensaje de error.
    "daphne",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "channels",
    "exams",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "exam_master.urls"
ASGI_APPLICATION = "exam_master.asgi.application"
WSGI_APPLICATION = "exam_master.wsgi.application"

# Carpeta para todo lo que la API escribe: base SQLite y registros. Por omision
# es BASE_DIR, que es lo correcto en desarrollo. Una instalacion la apunta a una
# ruta escribible, porque el codigo queda en Program Files y ahi un usuario
# estandar no puede escribir: crear el directorio de registros lanzaba al
# importar este modulo y el servidor moria antes de abrir el socket.
DATA_DIR = Path(os.getenv("AVACOM_DATA_DIR") or BASE_DIR)

# El prototipo replica el modelo relacional SQLite entregado. Mantener un único
# motor reduce fallos en la pantalla OPS y permite que el instalador sea autónomo.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": DATA_DIR / "db.sqlite3"}}

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "exams.exceptions.api_exception_handler",
    "COERCE_DECIMAL_TO_STRING": False,
}

CORS_ALLOW_ALL_ORIGINS = DEBUG
TIME_ZONE = "America/Bogota"
USE_TZ = True
LANGUAGE_CODE = "es-co"
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOG_DIR = DATA_DIR / "logs"

# Un destino de registro que no se puede crear NUNCA debe tumbar la API: el
# handler de archivo se abre al configurar el logging, durante el arranque de
# Django, asi que un fallo aqui mata el proceso antes de que escuche. Si la
# carpeta no se puede preparar se sigue con la consola y se avisa.
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_TO_FILE = os.access(LOG_DIR, os.W_OK)
except OSError:
    _LOG_TO_FILE = False
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"standard": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
        "file": {"class": "logging.handlers.RotatingFileHandler", "filename": LOG_DIR / "api.log", "maxBytes": 2_000_000, "backupCount": 3, "formatter": "standard"},
    },
    # DJANGO_LOG_LEVEL=WARNING deja la salida limpia al ejecutar las pruebas.
    "root": {"handlers": ["console", "file"] if _LOG_TO_FILE else ["console"],
             "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}

if not _LOG_TO_FILE:
    LOGGING["handlers"].pop("file")
    print(f"AVISO: sin registro en archivo, {LOG_DIR} no es escribible.")

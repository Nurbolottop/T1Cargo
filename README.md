
# CargoBot — Backend

Backend проекта **CargoBot**: Django-приложение для управления карго-отправками (менеджерская панель), Telegram WebApp для клиентов и Telegram-бот. В инфраструктуру также входят Postgres, Redis и Celery.

## Стек

- **Python** 3.11
- **Django** 5.2
- **PostgreSQL** 14
- **Redis** 6
- **Celery** 5.4
- **Telegram bot** (aiogram)

## Сервисы (docker-compose)

Файлы:

- `docker/docker-compose.yml` — разработка
- `docker/docker-compose.prod.yml` — продакшн

Сервисы:

- `db_cargo` — Postgres
- `redis_cargo` — Redis
- `web_cargo` — Django (dev: `runserver`, prod: `gunicorn`)
- `celery_worker_cargo` — Celery worker
- `telegram_bot` — запуск бота (`python manage.py bot`)
- `scheduler_cargo` — прод-сервис для ежедневного запуска начислений (см. ниже)

## Переменные окружения

В корне `Backend/` есть `.envtest` — пример переменных окружения. Создай `.env` на его основе.

Минимально необходимые:

- `SECRET_KEY`
- `DEBUG` (`True` только для разработки)
- `ALLOWED_HOSTS` (через запятую)
- `CSRF_TRUSTED_ORIGINS` (через запятую, опционально; важно для https-доменов)
- `LANGUAGE_CODE`, `TIME_ZONE`

Postgres:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST` — **должен совпадать с именем сервиса БД в compose** (по умолчанию: `db_cargo`)
- `POSTGRES_PORT` — обычно `5432` внутри docker-сети

Опционально:

- `BOT_AUTORELOAD` — если `true/1`, бот будет запускаться с autoreload
- `RUN_MAKEMIGRATIONS` — если `true/1`, контейнер выполнит `makemigrations` (по умолчанию пропускается)

## Быстрый старт (development)

1) Создай `.env`:

```bash
cp .envtest .env
```

2) Запусти dev-сборку:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Порты по умолчанию (dev):

- Django: `http://127.0.0.1:8084` (контейнер слушает `8082`)
- Postgres: `localhost:5435`
- Redis: `localhost:6389`

## Первый запуск (инициализация)

После старта контейнеров:

1) Создай суперпользователя Django:

```bash
docker compose -f docker/docker-compose.yml exec web_cargo python manage.py createsuperuser
```

2) Открой админку:

- `http://127.0.0.1:8084/admin/`

3) Создай запись **Settings** (в админке), т.к. бот читает настройки и токен из БД:

- Включи `is_bot_enabled`
- Заполни `telegram_token`
- При необходимости заполни ссылку `registration_webapp_url`

## Основные URL

- **Admin**: `/admin/`
- **Менеджерская панель** (вход): `/manager/login/`
- **Telegram WebApp**:
  - `/webapp/register/`
  - `/webapp/profile/`

## Полезные команды

Запуск бота (используется сервисом `telegram_bot`):

```bash
docker compose -f docker/docker-compose.yml exec web_cargo python manage.py bot
```

Начисление штрафов за хранение (команда есть, в prod запускается сервисом `scheduler_cargo` раз в сутки):

```bash
docker compose -f docker/docker-compose.yml exec web_cargo python manage.py charge_storage_penalties
docker compose -f docker/docker-compose.yml exec web_cargo python manage.py charge_storage_penalties --date 2026-01-01 --dry-run
```

Celery worker (обычно запускается как отдельный сервис):

```bash
docker compose -f docker/docker-compose.yml logs -f celery_worker_cargo
```

## Продакшн

```bash
docker compose -f docker/docker-compose.prod.yml up --build -d
```

По умолчанию web-сервис публикуется на `:8003` (контейнер слушает `8000`).

## Структура

- `app/` — Django проект (`core/` + приложения `apps/*`)
- `docker/` — Dockerfile и docker-compose
- `scripts/entrypoint.sh` — ожидание БД + миграции + collectstatic
- `.envtest` — пример переменных окружения

## Типовые проблемы

- **Нет соединения с БД**: проверь `POSTGRES_*` в `.env` и что `POSTGRES_HOST=db_cargo` (для текущего compose).
- **Бот не стартует**: создай запись `Settings` в админке и включи `is_bot_enabled`, заполни `telegram_token`.
- **Порты заняты**: поменяй внешние порты в `docker/docker-compose.yml`.


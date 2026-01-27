#!/bin/sh
set -e

echo "Начало инициализации базы данных..."

# Подождем некоторое время, чтобы убедиться, что сеть и база данных готовы
echo "Подождем 10 секунд, чтобы убедиться, что сеть и база данных готовы..."
sleep 10

# Ожидание доступности базы данных
echo "Ожидание доступности базы данных..."
until nc -z -v -w30 $POSTGRES_HOST $POSTGRES_PORT
do
  echo "Waiting for PostgreSQL database connection..."
  sleep 1
done

echo "База данных доступна. Создаём миграции..."
if [ "${RUN_MAKEMIGRATIONS:-}" = "1" ] || [ "${RUN_MAKEMIGRATIONS:-}" = "true" ] || [ "${RUN_MAKEMIGRATIONS:-}" = "True" ]; then
  python manage.py makemigrations --noinput
else
  echo "Пропускаем makemigrations (RUN_MAKEMIGRATIONS не установлен)"
fi

echo "Применяем миграции..."
python manage.py migrate --noinput

echo "Собираем статические файлы..."
python manage.py collectstatic --noinput

# Запускаем переданную команду
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
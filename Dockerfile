# Railway-optimized Dockerfile
# Используем Python 3.12 (рекомендованная версия на Railway)
FROM python:3.12-slim

WORKDIR /app

# Копируем requirements
COPY requirements.txt .

# Быстрая установка зависимостей
RUN pip install --no-cache-dir --timeout=180 \
    -r requirements.txt \
    2>&1 | tail -5

# Копируем весь код
COPY . .

# Создаём папку для данных
RUN mkdir -p /app/data

# Railway передаёт порт через $PORT
ENV PORT=8080
EXPOSE 8080

CMD ["python", "bot.py"]

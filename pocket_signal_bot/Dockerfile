# Railway-optimized Dockerfile
# Используем полный образ — никаких сборок с нуля
FROM python:3.11

WORKDIR /app

# Копируем requirements
COPY requirements.txt .

# Устанавливаем всё через двоичные пакеты (быстро, без компиляции)
RUN pip install --no-cache-dir --timeout=180 --only-binary :all: \
    aiogram aiohttp aiosqlite sqlalchemy pandas pandas-ta numpy \
    apscheduler python-dotenv loguru \
    fastapi uvicorn python-multipart \
    scikit-learn matplotlib seaborn joblib pydantic \
    xxhash 2>&1 | tail -5

# Устанавливаем xgboost отдельно (у него есть колёса)
RUN pip install --no-cache-dir --timeout=180 xgboost 2>&1 | tail -3

# Копируем весь код
COPY . .

# Создаём папку для данных
RUN mkdir -p /app/data

# Railway передаёт порт через $PORT
ENV PORT=8080
EXPOSE 8080

CMD ["python", "bot.py"]

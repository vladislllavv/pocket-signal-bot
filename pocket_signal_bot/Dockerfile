# ---- Build ----
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---- Run ----
FROM python:3.11-slim

WORKDIR /app

# Утилиты для дебага
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Копируем установленные пакеты из builder
COPY --from=builder /root/.local /root/.local

# Копируем код
COPY . .

# Создаём директорию для данных
RUN mkdir -p /app/data

# PATH для pip --user
ENV PATH=/root/.local/bin:$PATH

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import app; print('ok')" || exit 1

ENTRYPOINT ["python", "bot.py"]

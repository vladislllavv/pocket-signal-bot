FROM python:3.11

WORKDIR /app

COPY requirements.txt .

# Простая установка без флагов
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV PORT=8080
EXPOSE 8080

CMD ["python", "bot.py"]

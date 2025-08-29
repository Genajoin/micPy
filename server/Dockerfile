FROM python:3.12-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование requirements.txt и установка Python зависимостей
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY server/ .
COPY common/ ./common

# Создание non-root пользователя
RUN useradd -m -u 1000 micpy && chown -R micpy:micpy /app
USER micpy

EXPOSE 8000

CMD ["python", "main.py"]
# Один образ для GPU и CPU: устройство выбирается переменной WHISPER_DEVICE
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Библиотеки CUDA из pip-пакетов nvidia-* (драйвер пробрасывает nvidia runtime)
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib
ENV HF_HOME=/models
ENV PYTHONUNBUFFERED=1

COPY app.py .

EXPOSE 5093
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import json,urllib.request; assert json.load(urllib.request.urlopen('http://localhost:5093/health'))['status']=='healthy'"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5093"]

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias del sistema (ffmpeg requerido por el proyecto).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

EXPOSE 8765

# Render/Railway inyectan PORT; fallback local a 8765.
CMD ["sh", "-c", "uvicorn web_server:app --host 0.0.0.0 --port ${PORT:-8765}"]

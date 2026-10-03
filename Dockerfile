FROM python:3.11-slim

# Installation de FFmpeg et des polices requises pour les sous-titres
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    edge-tts \
    python-multipart

COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
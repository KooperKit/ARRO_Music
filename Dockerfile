FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    musescore3 \
    xvfb \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV QT_QPA_PLATFORM=offscreen
ENV DISPLAY=:99

WORKDIR /app

RUN pip install --no-cache-dir \
    flask \
    flask-cors \
    requests \
    yt-dlp \
    basic-pitch==0.2.6 \
    tensorflow==2.12.0 \
    music21 \
    pretty_midi \
    numpy==1.23.5

# LINE@ 預留（取消註解即可）
# RUN pip install line-bot-sdk

COPY app.py .
COPY transcribe.py .

RUN mkdir -p /app/scripts /app/output \
    && cp /app/transcribe.py /app/scripts/transcribe.py

EXPOSE 8080

CMD ["python", "app.py"]

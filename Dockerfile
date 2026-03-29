FROM python:3.10-slim

# 系統套件
RUN apt-get update && apt-get install -y \
    ffmpeg \
    musescore3 \
    xvfb \
    curl \
    && rm -rf /var/lib/apt/lists/*

# MuseScore 無頭模式
ENV QT_QPA_PLATFORM=offscreen
ENV DISPLAY=:99

WORKDIR /app

# Python 套件 — 指定版本避免衝突
RUN pip install --no-cache-dir \
    flask==3.0.3 \
    flask-cors==4.0.1 \
    requests==2.31.0 \
    yt-dlp==2024.8.6 \
    basic-pitch==0.2.6 \
    tensorflow==2.12.0 \
    music21==9.3.0 \
    pretty_midi==0.2.10 \
    numpy==1.23.5 \
    # ── LINE@ 預留套件（取消註解即可啟用）──
    # line-bot-sdk==3.11.0 \
    && true

# 複製程式碼
COPY app.py .
COPY transcribe.py .

# 建立必要目錄
RUN mkdir -p /app/scripts /app/output \
    && cp /app/transcribe.py /app/scripts/transcribe.py

EXPOSE 8080

CMD ["python", "app.py"]

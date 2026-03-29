# 確保第一行是基礎鏡像，不讓 Zeabur 誤判
FROM python:3.9-slim

# 更新套件並安裝實質運算工具
RUN apt-get update && apt-get install -y \
    ffmpeg \
    musescore3 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 預先安裝依賴以利用快取
RUN pip install --no-cache-dir flask music21 basicpitch yt-dlp

COPY . .

# 這是關鍵：讓 MuseScore 能在無顯示器環境跑
ENV QT_QPA_PLATFORM=offscreen

EXPOSE 5000

# 啟動命令
CMD ["python", "main.py"]

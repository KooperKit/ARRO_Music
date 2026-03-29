# 使用 Python 基礎環境
FROM python:3.9-slim

# 安裝音樂處理必備套件：ffmpeg, MuseScore, 虛擬顯示器
RUN apt-get update && apt-get install -y \
    ffmpeg \
    musescore3 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安裝 Python 依賴庫（對應你上傳的 transcribe.py）
RUN pip install --no-cache-dir yt-dlp basic-pitch music21 pretty-midi flask

# 複製所有檔案（包含你的 transcribe.py）
COPY . .

# 設定 MuseScore 可以在無螢幕環境執行
ENV QT_QPA_PLATFORM=offscreen

# 開放 API 埠位
EXPOSE 5000

# 啟動命令
CMD ["python", "transcribe.py"]

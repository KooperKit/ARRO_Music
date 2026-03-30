"""
禪奈資工二部 — 琴譜構造器 (HF 分流整合版)
app.py v3.1 - 由 Zeabur 派發任務至 Hugging Face
"""
import os, time, json, subprocess, requests, threading, glob, base64
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OUTPUT_DIR  = Path("/app/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- 設定區 ---
RESEND_API = "https://api.resend.com/emails"
RESEND_KEY = os.environ.get("RESEND_API_KEY", "re_QteTo8YT_aKshE1vZQcj8ypzvdbELbhCk")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")
# 請在 Zeabur 環境變數設定此網址，例如：https://kkn8n29-jhana-transcribe.hf.space
HF_SPACE_URL = os.environ.get("HF_SPACE_URL", "https://你的HF名稱-你的Space名稱.hf.space")

tasks = {}

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status":"healthy","service":"禪奈分流引擎","version":"3.1"}), 200

# (保留你原本的 /webhook/jhanamusic, /status, /download 邏輯不變)
@app.route('/webhook/jhanamusic', methods=['POST','OPTIONS'])
def transcribe_webhook():
    if request.method == 'OPTIONS': return '', 204
    data = request.get_json(silent=True) or {}
    url = data.get('url','').strip()
    email = data.get('email','').strip()
    if not url or not email:
        return jsonify({"success":False,"error":"缺少 URL 或 Email"}), 400
    
    task_id = f"task_{int(time.time())}_{os.urandom(3).hex()}"
    tasks[task_id] = {"status":"processing","email":email,"created":time.time()}
    
    # 啟動分流執行緒
    threading.Thread(target=_run_dispatch_logic, args=(task_id, url, email, data), daemon=True).start()
    
    return jsonify({
        "success":True,"taskId":task_id,
        "message":"已交給 AI 引擎處理，請留意電子信箱",
        "statusUrl":f"https://jhanamusic.zeabur.app/status/{task_id}"
    }), 200

def _run_dispatch_logic(task_id, url, email, original_data):
    try:
        print(f"[{task_id}] 正在發送請求至 HF Space...")
        # 1. 呼叫 Hugging Face AI 運算 (這步取代了原本重負載的 transcribe.py AI 部份)
        hf_api = f"{HF_SPACE_URL.rstrip('/')}/api/predict"
        response = requests.post(hf_api, json={
            "data": [url, original_data.get('key','C'), original_data.get('difficulty','intermediate'), "{}"]
        }, timeout=600)
        
        if response.status_code != 200:
            raise RuntimeError(f"HF 引擎回應錯誤: {response.text}")

        res_json = json.loads(response.json()['data'][0])
        if not res_json.get('success'):
            raise RuntimeError(f"AI 轉譜失敗: {res_json.get('error')}")

        # 2. 拿回 MIDI 進行畫譜 (PDF)
        # 將 base64 轉回 MIDI 檔案
        midi_path = OUTPUT_DIR / f"{task_id}.mid"
        pdf_path = OUTPUT_DIR / f"{task_id}.pdf"
        midi_path.write_bytes(base64.b64decode(res_json['midi_b64']))

        print(f"[{task_id}] MIDI 已就緒，正在生成 PDF...")
        # 呼叫 MuseScore 進行畫譜 (這部分在 Zeabur 跑很快，不吃資源)
        subprocess.run(["mscore3", "-o", str(pdf_path), str(midi_path)], check=True)

        # 3. 更新狀態並寄信
        output = {
            "success": True,
            "song_title": res_json.get('title', '我的客製化樂譜'),
            "pdf_path": str(pdf_path),
            "filename": f"{task_id}.pdf",
            "key": original_data.get('key','C'),
            "difficulty": original_data.get('difficulty','intermediate')
        }
        tasks[task_id].update({"status":"done", "songTitle": output['song_title']})
        _send_email(email, output, task_id)
        
    except Exception as e:
        print(f"[{task_id}] 錯誤: {str(e)}")
        tasks[task_id] = {"status":"error","error":str(e)}

# (保留你原本的 _send_email, status, download 等路由)
# ... [此處省略其餘不變的代碼] ...

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT",8080)), debug=False)

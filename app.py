"""
禪奈資工二部 — 琴譜構造器
app.py v3.0
"""
import os, time, json, subprocess, requests, threading, glob
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

OUTPUT_DIR  = Path("/app/output")
SCRIPTS_DIR = Path("/app/scripts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESEND_API = "https://api.resend.com/emails"
RESEND_KEY = os.environ.get("RESEND_API_KEY", "re_QteTo8YT_aKshE1vZQcj8ypzvdbELbhCk")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")

# LINE@ 預留
# LINE_CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")
# LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

tasks = {}

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status":"healthy","service":"禪奈資工二部 — 琴譜構造器","version":"3.0"}), 200

@app.route('/webhook/jhanamusic', methods=['POST','OPTIONS'])
def transcribe_webhook():
    if request.method == 'OPTIONS':
        return '', 204
    data = request.get_json(silent=True) or {}
    url        = data.get('url','').strip()
    email      = data.get('email','').strip()
    key        = data.get('key','C')
    difficulty = data.get('difficulty','intermediate')
    features   = data.get('features',{})
    if not url:
        return jsonify({"success":False,"error":"缺少音源 URL"}), 400
    if not email or '@' not in email:
        return jsonify({"success":False,"error":"缺少有效 Email"}), 400
    if difficulty not in ('beginner','intermediate','advanced'):
        difficulty = 'intermediate'
    task_id = f"task_{int(time.time())}_{os.urandom(3).hex()}"
    tasks[task_id] = {"status":"processing","email":email,"created":time.time()}
    threading.Thread(target=_run_transcribe, args=(task_id,url,email,key,difficulty,features), daemon=True).start()
    return jsonify({
        "success":True,"taskId":task_id,
        "message":"轉譜已開始，約 3–5 分鐘完成後 PDF 會寄到信箱",
        "statusUrl":f"https://jhanamusic.zeabur.app/status/{task_id}",
        "downloadUrl":f"https://jhanamusic.zeabur.app/download/{task_id}"
    }), 200

@app.route('/status/<task_id>', methods=['GET'])
def task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        matches = glob.glob(str(OUTPUT_DIR / f"{task_id}*.pdf"))
        if matches:
            return jsonify({"status":"done","downloadReady":True}), 200
        return jsonify({"status":"not_found"}), 404
    return jsonify(task), 200

@app.route('/download/<task_id>', methods=['GET'])
def download(task_id):
    matches = glob.glob(str(OUTPUT_DIR / f"{task_id}*.pdf"))
    if not matches:
        return jsonify({"error":"找不到檔案，可能尚未完成或已過期"}), 404
    return send_file(matches[0], as_attachment=True)

# ── LINE@ Webhook 預留區 ──────────────────────────────────
# 啟用步驟：
# 1. Dockerfile 取消註解 line-bot-sdk
# 2. 環境變數填入 LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN
# 3. 取消下方整個 function 的註解
# 4. Line Developers → Webhook URL：https://jhanamusic.zeabur.app/webhook/line
#
# @app.route('/webhook/line', methods=['POST'])
# def line_webhook():
#     from linebot.v3 import WebhookHandler
#     from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
#     from linebot.v3.webhooks import MessageEvent, TextMessageContent
#     import hmac, hashlib, base64
#     body = request.get_data(as_text=True)
#     signature = request.headers.get('X-Line-Signature','')
#     hash = hmac.new(LINE_CHANNEL_SECRET.encode(), body.encode(), hashlib.sha256).digest()
#     if base64.b64encode(hash).decode() != signature:
#         return 'Invalid signature', 400
#     handler = WebhookHandler(LINE_CHANNEL_SECRET)
#     @handler.add(MessageEvent, message=TextMessageContent)
#     def handle_message(event):
#         text = event.message.text.strip()
#         config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
#         with ApiClient(config) as api_client:
#             line_api = MessagingApi(api_client)
#             if 'youtube.com' in text or 'youtu.be' in text:
#                 task_id = f"task_{int(time.time())}_{os.urandom(3).hex()}"
#                 tasks[task_id] = {"status":"processing","line_user":event.source.user_id}
#                 threading.Thread(target=_run_transcribe, args=(task_id,text,None,'C','intermediate',{}), daemon=True).start()
#                 line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token,
#                     messages=[TextMessage(text=f"✅ 收到！轉譜中約 3–5 分鐘\n完成後點此下載：\nhttps://jhanamusic.zeabur.app/download/{task_id}")]))
#             else:
#                 line_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token,
#                     messages=[TextMessage(text="請傳入 YouTube 連結，我幫你轉成鋼琴譜 🎹")]))
#     handler.handle(body, signature)
#     return 'OK', 200

def _run_transcribe(task_id, url, email, key, difficulty, features):
    cmd = ["python3", str(SCRIPTS_DIR/"transcribe.py"),
        "--task-id", task_id, "--url", url, "--key", key, "--difficulty", difficulty,
        "--fingering",     str(int(features.get('fingering',True))),
        "--chord",         str(int(features.get('chord',True))),
        "--pedal",         str(int(features.get('pedal',False))),
        "--tempo",         str(int(features.get('tempo',False))),
        "--simplify-left", str(int(features.get('simplifyLeft',False))),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = json.loads(result.stdout.strip())
        if output.get('success'):
            tasks[task_id] = {"status":"done","email":email,
                "songTitle":output.get('song_title',''),"pages":output.get('pages',1),
                "generationTime":output.get('generation_time',0),
                "key":key,"difficulty":difficulty,"filename":output.get('filename',''),
                "downloadUrl":f"https://jhanamusic.zeabur.app/download/{task_id}"}
            if email:
                _send_email(email, output, task_id)
        else:
            tasks[task_id] = {"status":"error","error":output.get('error','轉譜失敗')}
    except subprocess.TimeoutExpired:
        tasks[task_id] = {"status":"error","error":"轉譜超時（超過 10 分鐘）"}
    except Exception as e:
        tasks[task_id] = {"status":"error","error":str(e)}

def _send_email(to_email, output, task_id):
    try:
        import base64
        pdf_path = Path(output['pdf_path'])
        if not pdf_path.exists(): return
        diff_label = {'beginner':'初級','intermediate':'中級','advanced':'高級'}.get(output.get('difficulty',''),'')
        pdf_b64 = base64.b64encode(pdf_path.read_bytes()).decode()
        requests.post(RESEND_API, headers={"Authorization":f"Bearer {RESEND_KEY}","Content-Type":"application/json"},
            json={"from":FROM_EMAIL,"to":[to_email],
                "subject":f"🎹 客製化樂譜完成 — {output.get('song_title','')} ({output.get('key','')} 調 · {diff_label})",
                "html":f"<p>您的客製化樂譜已完成，PDF 請見附件。</p><p>曲目：{output.get('song_title','')}<br>調性：{output.get('key','')} 調<br>難度：{diff_label}<br>頁數：{output.get('pages','')} 頁</p>",
                "attachments":[{"filename":output['filename'],"content":pdf_b64,"content_type":"application/pdf"}]
            }, timeout=30)
    except Exception as e:
        print(f"[EMAIL ERROR] {e}", flush=True)

@app.route('/transcribe', methods=['POST'])
def legacy():
    return transcribe_webhook()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT",8080)), debug=False)

"""
禪奈資工二部 — 琴譜構造器
app.py — Flask API Server

修正項目：
  1. os.time.time() → time.time() (原版 bug)
  2. 接收前端完整 JSON 格式（url/email/key/difficulty/features）
  3. 回傳前端需要的格式（success/pages/generationTime/songTitle）
  4. 整合 Resend 寄送 PDF Email 附件
  5. CORS 支援（讓前端 HTML 可以跨域呼叫）
  6. /health 健康檢查
  7. 錯誤處理完整化
"""

import os
import time
import json
import subprocess
import requests
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # 允許所有來源，讓前端 HTML 可以呼叫

# ── 設定 ──────────────────────────────────────────────────
OUTPUT_DIR   = Path("/app/output")
SCRIPTS_DIR  = Path("/app/scripts")
RESEND_API   = "https://api.resend.com/emails"
RESEND_KEY   = os.environ.get("RESEND_API_KEY", "re_QteTo8YT_aKshE1vZQcj8ypzvdbELbhCk")
FROM_EMAIL   = os.environ.get("FROM_EMAIL", "noreply@jhanamusic.com")  # 需在 Resend 驗證網域

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ── 健康檢查 ──────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "禪奈資工二部 — 琴譜構造器",
        "version": "2.1"
    }), 200


# ── 主要 Webhook 端點 ─────────────────────────────────────
@app.route('/webhook/jhanamusic', methods=['POST', 'OPTIONS'])
def transcribe_webhook():
    # CORS preflight
    if request.method == 'OPTIONS':
        return '', 204

    data = request.get_json(silent=True) or {}

    # ── 解析參數 ──────────────────────────────────────────
    url        = data.get('url', '').strip()
    email      = data.get('email', '').strip()
    key        = data.get('key', 'C')
    difficulty = data.get('difficulty', 'intermediate')
    features   = data.get('features', {})

    # ── 驗證 ──────────────────────────────────────────────
    if not url:
        return jsonify({"success": False, "error": "缺少音源 URL"}), 400
    if not email or '@' not in email:
        return jsonify({"success": False, "error": "缺少或無效的 Email"}), 400
    if difficulty not in ('beginner', 'intermediate', 'advanced'):
        difficulty = 'intermediate'

    # ── 建立任務 ID ───────────────────────────────────────
    task_id = f"task_{int(time.time())}_{os.urandom(3).hex()}"

    # ── 執行轉譜腳本 ──────────────────────────────────────
    cmd = [
        "python3", str(SCRIPTS_DIR / "transcribe.py"),
        "--task-id",      task_id,
        "--url",          url,
        "--key",          key,
        "--difficulty",   difficulty,
        "--fingering",    str(int(features.get('fingering', True))),
        "--chord",        str(int(features.get('chord', True))),
        "--pedal",        str(int(features.get('pedal', False))),
        "--tempo",        str(int(features.get('tempo', False))),
        "--simplify-left", str(int(features.get('simplifyLeft', False))),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=360  # 6 分鐘上限
        )
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "轉譜超時（超過 6 分鐘），請嘗試較短的曲目"}), 504
    except Exception as e:
        return jsonify({"success": False, "error": f"腳本執行失敗: {str(e)}"}), 500

    # ── 解析腳本輸出 ───────────────────────────────────────
    if result.returncode != 0:
        error_detail = result.stderr[-500:] if result.stderr else "未知錯誤"
        return jsonify({
            "success": False,
            "error": f"轉譜失敗: {error_detail}"
        }), 500

    try:
        script_output = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return jsonify({
            "success": False,
            "error": f"腳本輸出解析失敗: {result.stdout[:200]}"
        }), 500

    if not script_output.get('success'):
        return jsonify({
            "success": False,
            "error": script_output.get('error', '轉譜失敗')
        }), 500

    # ── 讀取 PDF 並用 Resend 寄送 ─────────────────────────
    pdf_path = Path(script_output['pdf_path'])
    if pdf_path.exists():
        email_sent = _send_pdf_email(
            to_email       = email,
            pdf_path       = pdf_path,
            pdf_filename   = script_output['filename'],
            song_title     = script_output.get('song_title', '未知曲目'),
            key            = key,
            difficulty     = difficulty,
            pages          = script_output.get('pages', 1),
            generation_time= script_output.get('generation_time', 0)
        )
    else:
        email_sent = False

    # ── 回傳給前端 ────────────────────────────────────────
    return jsonify({
        "success":        True,
        "taskId":         task_id,
        "email":          email,
        "emailSent":      email_sent,
        "songTitle":      script_output.get('song_title', '未知曲目'),
        "pages":          script_output.get('pages', 1),
        "generationTime": script_output.get('generation_time', 0),
        "key":            key,
        "difficulty":     difficulty,
        "filename":       script_output.get('filename', ''),
        "message":        f"樂譜已生成完成，PDF 已寄至 {email}"
    }), 200


# ── Resend 寄送函數 ───────────────────────────────────────
def _send_pdf_email(
    to_email, pdf_path, pdf_filename,
    song_title, key, difficulty, pages, generation_time
):
    """使用 Resend API 寄送 PDF 附件"""
    try:
        import base64
        with open(pdf_path, 'rb') as f:
            pdf_b64 = base64.b64encode(f.read()).decode('utf-8')

        diff_label = {'beginner':'初級', 'intermediate':'中級', 'advanced':'高級'}.get(difficulty, difficulty)

        html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>
  body {{ font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif;
         background: #F9FAFB; color: #1D1D1F; margin: 0; padding: 0; }}
  .wrap {{ max-width: 540px; margin: 40px auto; background: white;
           border: 1px solid #E5E7EB; border-radius: 12px; overflow: hidden; }}
  .top  {{ background: #2D6A4F; padding: 28px 32px; }}
  .top h1 {{ color: white; margin: 0; font-size: 20px; font-weight: 700; }}
  .top p  {{ color: rgba(255,255,255,0.75); margin: 4px 0 0; font-size: 11px;
             letter-spacing: 0.1em; font-family: monospace; }}
  .body {{ padding: 28px 32px; }}
  .body p {{ font-size: 14px; line-height: 1.7; color: #374151; margin-bottom: 20px; }}
  .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
  .info-table td {{ padding: 9px 12px; font-size: 12px; border-bottom: 1px solid #F3F4F6; }}
  .info-table .label {{ color: #9CA3AF; font-family: monospace; width: 35%; }}
  .info-table .val   {{ color: #2D6A4F; font-weight: 600; }}
  .notice {{ background: #F0FBF3; border: 1px solid #D8F3DC; border-radius: 8px;
             padding: 12px 16px; font-size: 11px; color: #2D6A4F; font-family: monospace; }}
  .foot {{ padding: 16px 32px; font-size: 10px; color: #9CA3AF;
           border-top: 1px solid #F3F4F6; text-align: center; font-family: monospace; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <h1>🎹 琴譜構造器</h1>
    <p>禪奈資工二部 · JHANAMUSIC · SCORE ARCHITECT</p>
  </div>
  <div class="body">
    <p>您的客製化樂譜已生成完成，PDF 附件請見附件。</p>
    <table class="info-table">
      <tr><td class="label">曲目</td><td class="val">{song_title}</td></tr>
      <tr><td class="label">調性</td><td class="val">{key} {'小調' if key.endswith('m') else '大調'}</td></tr>
      <tr><td class="label">難度</td><td class="val">{diff_label}</td></tr>
      <tr><td class="label">頁數</td><td class="val">{pages} 頁 · A4</td></tr>
      <tr><td class="label">生成時間</td><td class="val">{generation_time} 秒</td></tr>
    </table>
    <div class="notice">📎 附件：{pdf_filename}</div>
  </div>
  <div class="foot">此為系統自動寄送，請勿回覆 · 生成結果僅供個人教學使用 · 禪奈資工二部 © 2026</div>
</div>
</body>
</html>
        """

        payload = {
            "from":    FROM_EMAIL,
            "to":      [to_email],
            "subject": f"🎹 客製化樂譜已完成 — {song_title} ({key} 調 · {diff_label})",
            "html":    html_body,
            "attachments": [{
                "filename":    pdf_filename,
                "content":     pdf_b64,
                "content_type":"application/pdf"
            }]
        }

        resp = requests.post(
            RESEND_API,
            headers={
                "Authorization": f"Bearer {RESEND_KEY}",
                "Content-Type":  "application/json"
            },
            json=payload,
            timeout=30
        )

        return resp.status_code == 200

    except Exception as e:
        print(f"[EMAIL ERROR] {e}", flush=True)
        return False


# ── 備用路由（相容舊版 /transcribe）──────────────────────
@app.route('/transcribe', methods=['POST'])
def transcribe_legacy():
    """相容舊版端點，轉發至新端點"""
    return transcribe_webhook()


# ── 啟動 ──────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

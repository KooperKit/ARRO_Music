from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    # 取得參數
    url = data.get('url')
    task_id = data.get('task_id', f"task_{int(os.time.time())}")
    
    if not url:
        return jsonify({"error": "Missing URL"}), 400

    # 呼叫你原本寫好的 transcribe.py
    try:
        cmd = [
            "python3", "transcribe.py",
            "--task-id", task_id,
            "--url", url,
            "--key", data.get('key', 'C'),
            "--difficulty", data.get('difficulty', 'intermediate'),
            "--fingering", str(data.get('fingering', 1)),
            "--chord", str(data.get('chord', 1)),
            "--pedal", str(data.get('pedal', 0)),
            "--tempo", str(data.get('tempo', 0)),
            "--simplify-left", str(data.get('simplify-left', 0))
        ]
        # 執行並獲取結果
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
        return jsonify({"success": True, "output": result})
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": e.output.decode('utf-8')}), 500

if __name__ == '__main__':
    # 監聽 0.0.0.0 確保外部可以存取
    app.run(host='0.0.0.0', port=8080)

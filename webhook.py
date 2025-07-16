from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

# Cấu hình webhook
SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/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'  # <-- Cập nhật
TELEGRAM_BOT_TOKEN = '5003750423:AAGwHyrM69uj5uNEzMDgoq_M2i9y1-ZkXTs'
TELEGRAM_CHAT_ID = '-608003539'

# Hàm lọc thông tin từ alert text
def extract_alert_info(text):
    data = {}

    # Dùng regex để lấy thông tin từ đoạn văn bản
    value_match = re.search(r'Value:\s*(.+)', text)
    if value_match:
        data['Value'] = value_match.group(1).strip()

    labels_match = re.findall(r'-\s*(\w+)\s*=\s*(.+)', text)
    for key, value in labels_match:
        data[key] = value.strip()

    annotations_match = re.findall(r'-\s*(\w+)\s*=\s*(.+)', text)
    for key, value in annotations_match:
        if key in ['description', 'summary']:
            data[key] = value.strip()

    return data

# Gửi thông báo lên Slack
def send_to_slack(alert_data):
    text = "\n".join([f"*{k}*: {v}" for k, v in alert_data.items()])
    payload = {"text": f"🚨 *Grafana Alert* 🚨\n{text}"}
    requests.post(SLACK_WEBHOOK_URL, json=payload)

# Gửi thông báo lên Telegram
def send_to_telegram(alert_data):
    text = "\n".join([f"{k}: {v}" for k, v in alert_data.items()])
    message = f"🚨 *Grafana Alert* 🚨\n{text}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

# Webhook nhận cảnh báo từ Grafana
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "Dữ liệu không hợp lệ"}), 400

    full_alert_text = data['message']
    alert_info = extract_alert_info(full_alert_text)

    # Gửi đi các kênh
    send_to_slack(alert_info)
    send_to_telegram(alert_info)

    return jsonify({"status": "Alert received and forwarded"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

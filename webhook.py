from flask import Flask, request, jsonify
import requests
import re
import json
from datetime import datetime
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Cấu hình webhook
SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/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'
TELEGRAM_BOT_TOKEN = '5003750423:AAGwHyrM69uj5uNEzMDgoq_M2i9y1-ZkXTs'
TELEGRAM_CHAT_ID = '-608003539'

# Emoji cho các trạng thái alert
ALERT_EMOJI = {
    'firing': '🚨',
    'resolved': '✅',
    'critical': '💥',
    'warning': '⚠️',
    'info': 'ℹ️',
    'ok': '✅'
}

# Màu sắc cho Slack
ALERT_COLORS = {
    'firing': '#FF0000',
    'resolved': '#00FF00',
    'critical': '#FF0000',
    'warning': '#FFA500',
    'info': '#0000FF',
    'ok': '#00FF00'
}

def extract_alert_info(data):
    """Trích xuất thông tin alert từ Grafana payload"""
    alerts = []
    
    # Xử lý format mới của Grafana
    if 'alerts' in data:
        for alert in data['alerts']:
            alert_info = {
                'title': alert.get('labels', {}).get('alertname', 'Unknown Alert'),
                'status': alert.get('status', 'unknown'),
                'severity': alert.get('labels', {}).get('severity', 'info'),
                'instance': alert.get('labels', {}).get('instance', 'N/A'),
                'job': alert.get('labels', {}).get('job', 'N/A'),
                'description': alert.get('annotations', {}).get('description', 'No description'),
                'summary': alert.get('annotations', {}).get('summary', 'No summary'),
                'value': alert.get('annotations', {}).get('value', 'N/A'),
                'startsAt': alert.get('startsAt', ''),
                'endsAt': alert.get('endsAt', ''),
                'fingerprint': alert.get('fingerprint', ''),
                'labels': alert.get('labels', {}),
                'annotations': alert.get('annotations', {})
            }
            alerts.append(alert_info)
    
    # Xử lý format cũ (fallback)
    elif 'message' in data:
        alert_info = extract_alert_info_legacy(data['message'])
        alerts.append(alert_info)
    
    return alerts

def extract_alert_info_legacy(text):
    """Trích xuất thông tin từ text format cũ"""
    data = {
        'title': 'Grafana Alert',
        'status': 'firing',
        'severity': 'info',
        'instance': 'N/A',
        'job': 'N/A',
        'description': 'No description',
        'summary': 'No summary',
        'value': 'N/A'
    }

    # Regex patterns để trích xuất thông tin
    patterns = {
        'value': r'Value:\s*(.+)',
        'alertname': r'alertname\s*=\s*(.+)',
        'instance': r'instance\s*=\s*(.+)',
        'job': r'job\s*=\s*(.+)',
        'severity': r'severity\s*=\s*(.+)',
        'description': r'description\s*=\s*(.+)',
        'summary': r'summary\s*=\s*(.+)'
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if key == 'alertname':
                data['title'] = match.group(1).strip()
            else:
                data[key] = match.group(1).strip()

    return data

def format_slack_message(alerts):
    """Tạo message format đẹp cho Slack - Version đơn giản"""
    messages = []
    
    for alert in alerts:
        status = alert['status'].lower()
        severity = alert['severity'].lower()
        
        # Chọn emoji
        emoji = ALERT_EMOJI.get(status, ALERT_EMOJI.get(severity, '🔔'))
        
        # Tạo timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Tạo message đơn giản
        message = f"""
{emoji} *{alert['title']}*

*Status:* {alert['status'].upper()}
*Severity:* {alert['severity'].upper()}
*Instance:* {alert['instance']}
*Job:* {alert['job']}
*Value:* {alert['value']}
*Time:* {timestamp}

*Description:* {alert['description']}
*Summary:* {alert['summary']}

{'─' * 30}
"""
        messages.append(message)
    
    final_message = f"🚨 *Grafana Alert Notification* ({len(alerts)} alert{'s' if len(alerts) > 1 else ''})\n"
    final_message += "\n".join(messages)
    
    return {"text": final_message}

def format_telegram_message(alerts):
    """Tạo message format đẹp cho Telegram"""
    messages = []
    
    for alert in alerts:
        status = alert['status'].lower()
        severity = alert['severity'].lower()
        
        # Chọn emoji
        emoji = ALERT_EMOJI.get(status, ALERT_EMOJI.get(severity, '🔔'))
        
        # Tạo timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        message = f"""
{emoji} *{alert['title']}*

📊 *Status:* `{alert['status'].upper()}`
⚡ *Severity:* `{alert['severity'].upper()}`
🖥️ *Instance:* `{alert['instance']}`
🔧 *Job:* `{alert['job']}`
📈 *Value:* `{alert['value']}`
🕐 *Time:* `{timestamp}`

📝 *Description:*
{alert['description']}

📋 *Summary:*
{alert['summary']}

{'─' * 30}
"""
        messages.append(message)
    
    return "\n".join(messages)

def send_to_slack(alerts):
    """Gửi thông báo lên Slack với format đẹp"""
    try:
        payload = format_slack_message(alerts)
        
        # Log payload để debug
        logger.info(f"Sending to Slack: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            SLACK_WEBHOOK_URL, 
            json=payload, 
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        
        logger.info(f"Slack response status: {response.status_code}")
        logger.info(f"Slack response text: {response.text}")
        
        if response.status_code == 200:
            logger.info("Alert sent to Slack successfully")
        else:
            logger.error(f"Failed to send to Slack: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"Error sending to Slack: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

def send_to_telegram(alerts):
    """Gửi thông báo lên Telegram với format đẹp"""
    try:
        message = format_telegram_message(alerts)
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info("Alert sent to Telegram successfully")
        else:
            logger.error(f"Failed to send to Telegram: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Error sending to Telegram: {str(e)}")

def send_test_alert():
    """Gửi alert test để kiểm tra"""
    test_alerts = [{
        'title': 'Test Alert',
        'status': 'firing',
        'severity': 'warning',
        'description': 'This is a test alert to verify webhook functionality',
        'summary': 'Test alert summary',
        'value': '85.5%'
    }]
    
    send_to_slack(test_alerts)
    send_to_telegram(test_alerts)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook nhận cảnh báo từ Grafana"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data received"}), 400
            
        logger.info(f"Received webhook data: {json.dumps(data, indent=2)}")
        
        # Trích xuất thông tin alert
        alerts = extract_alert_info(data)
        
        if not alerts:
            return jsonify({"error": "No alerts found in data"}), 400
        
        # Gửi đến các kênh
        send_to_slack(alerts)
        send_to_telegram(alerts)
        
        return jsonify({
            "status": "success",
            "message": f"Processed {len(alerts)} alert(s) successfully"
        }), 200
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Endpoint để test webhook"""
    send_test_alert()
    return jsonify({"status": "Test alert sent"}), 200

@app.route('/test-slack', methods=['GET'])
def test_slack_only():
    """Test chỉ Slack để debug"""
    try:
        # Test với payload đơn giản nhất
        simple_payload = {"text": "🚨 Test message from webhook"}
        
        logger.info(f"Testing simple payload: {json.dumps(simple_payload)}")
        
        response = requests.post(
            SLACK_WEBHOOK_URL, 
            json=simple_payload, 
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response text: {response.text}")
        
        if response.status_code == 200:
            return jsonify({"status": "Slack test successful", "response": response.text}), 200
        else:
            return jsonify({
                "status": "Slack test failed", 
                "status_code": response.status_code,
                "response": response.text
            }), 400
            
    except Exception as e:
        logger.error(f"Error in Slack test: {str(e)}")
        return jsonify({"status": "Error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
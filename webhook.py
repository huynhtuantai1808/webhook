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
    """Trích xuất thông tin từ text format cũ - Cải tiến cho Zabbix/Grafana"""
    data = {
        'title': 'System Alert',
        'status': 'firing',
        'severity': 'warning',
        'instance': 'N/A',
        'job': 'N/A',
        'description': 'No description',
        'summary': 'No summary',
        'value': 'N/A',
        'host': 'N/A',
        'item': 'N/A',
        'item_key': 'N/A',
        'grafana_folder': 'N/A',
        'alertname': 'Unknown Alert'
    }

    # Trích xuất Value (có thể có nhiều giá trị B=, C=)
    value_match = re.search(r'Value:\s*(.+?)(?=Labels:|$)', text, re.DOTALL)
    if value_match:
        value_text = value_match.group(1).strip()
        # Parse multiple values như B=1.4444969984e+10, C=1
        values = []
        value_parts = re.findall(r'([A-Z])=([0-9.e+-]+)', value_text)
        for var, val in value_parts:
            try:
                # Convert scientific notation to readable format
                float_val = float(val)
                if float_val > 1e9:
                    readable_val = f"{float_val/1e9:.2f}GB"
                elif float_val > 1e6:
                    readable_val = f"{float_val/1e6:.2f}MB"
                elif float_val > 1e3:
                    readable_val = f"{float_val/1e3:.2f}KB"
                else:
                    readable_val = f"{float_val:.2f}"
                values.append(f"{var}={readable_val}")
            except:
                values.append(f"{var}={val}")
        
        data['value'] = ", ".join(values) if values else value_text

    # Trích xuất Labels
    labels_section = re.search(r'Labels:\s*(.+?)(?=Annotations:|$)', text, re.DOTALL)
    if labels_section:
        labels_text = labels_section.group(1)
        # Parse labels với format: - key = value
        label_matches = re.findall(r'-\s*(\w+)\s*=\s*(.+)', labels_text)
        for key, value in label_matches:
            key = key.strip()
            value = value.strip()
            
            if key == 'alertname':
                data['title'] = value
                data['alertname'] = value
            elif key == 'host':
                data['host'] = value
                data['instance'] = value  # Cũng set instance
            elif key == 'item':
                data['item'] = value
            elif key == 'item_key':
                data['item_key'] = value
            elif key == 'grafana_folder':
                data['grafana_folder'] = value
            elif key == 'severity':
                data['severity'] = value
            elif key == 'job':
                data['job'] = value
            else:
                data[key] = value

    # Trích xuất Annotations
    annotations_section = re.search(r'Annotations:\s*(.+?)

def format_slack_message(alerts):
    """Tạo message format đẹp cho Slack - Phiên bản cải tiến cho Zabbix"""
    messages = []
    
    for alert in alerts:
        status = alert['status'].lower()
        severity = alert['severity'].lower()
        
        # Chọn emoji dựa trên severity và item type
        if 'memory' in alert.get('item', '').lower() or 'ram' in alert.get('item', '').lower():
            emoji = '🧠'
        elif 'cpu' in alert.get('item', '').lower():
            emoji = '⚡'
        elif 'disk' in alert.get('item', '').lower():
            emoji = '💾'
        elif 'network' in alert.get('item', '').lower():
            emoji = '🌐'
        else:
            emoji = ALERT_EMOJI.get(status, ALERT_EMOJI.get(severity, '🔔'))
        
        # Tạo timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Format message với thông tin chi tiết
        message = f"""
{emoji} *{alert['title']}*

📊 *Status:* {alert['status'].upper()}
⚠️ *Severity:* {alert['severity'].upper()}
🖥️ *Host:* {alert['host']}
📋 *Item:* {alert['item']}
🔑 *Item Key:* {alert['item_key']}
📁 *Folder:* {alert['grafana_folder']}
📈 *Value:* {alert['value']}
🕐 *Time:* {timestamp}

📝 *Description:* {alert['description']}
📋 *Summary:* {alert['summary']}

{'─' * 40}
"""
        messages.append(message)
    
    final_message = f"🚨 *System Alert Notification* ({len(alerts)} alert{'s' if len(alerts) > 1 else ''})\n"
    final_message += "\n".join(messages)
    
    return {"text": final_message}

def format_telegram_message(alerts):
    """Tạo message format đẹp cho Telegram - Phiên bản cải tiến cho Zabbix"""
    messages = []
    
    for alert in alerts:
        status = alert['status'].lower()
        severity = alert['severity'].lower()
        
        # Chọn emoji dựa trên item type
        if 'memory' in alert.get('item', '').lower() or 'ram' in alert.get('item', '').lower():
            emoji = '🧠'
        elif 'cpu' in alert.get('item', '').lower():
            emoji = '⚡'
        elif 'disk' in alert.get('item', '').lower():
            emoji = '💾'
        elif 'network' in alert.get('item', '').lower():
            emoji = '🌐'
        else:
            emoji = ALERT_EMOJI.get(status, ALERT_EMOJI.get(severity, '🔔'))
        
        # Tạo timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Tạo severity badge
        severity_badge = {
            'critical': '🔴 CRITICAL',
            'warning': '🟡 WARNING', 
            'info': '🔵 INFO',
            'ok': '🟢 OK'
        }.get(severity.lower(), f'⚪ {severity.upper()}')
        
        message = f"""
{emoji} *{alert['title']}*

📊 *Status:* `{alert['status'].upper()}`
{severity_badge}
🖥️ *Host:* `{alert['host']}`
📋 *Item:* `{alert['item']}`
🔑 *Key:* `{alert['item_key']}`
📁 *Folder:* `{alert['grafana_folder']}`
📈 *Value:* `{alert['value']}`
🕐 *Time:* `{timestamp}`

📝 *Description:*
_{alert['description']}_

📋 *Summary:*  
_{alert['summary']}_

{'═' * 35}
"""
        messages.append(message)
    
    final_message = f"🚨 *SYSTEM ALERT* ({len(alerts)} alert{'s' if len(alerts) > 1 else ''})\n"
    final_message += "\n".join(messages)
    
    return final_message

def send_to_slack(alerts):
    """Gửi thông báo lên Slack với format đẹp"""
    try:
        # Tạm thời skip Slack nếu URL không hoạt động
        if not SLACK_WEBHOOK_URL or 'YOUR_' in SLACK_WEBHOOK_URL:
            logger.warning("Slack webhook URL not configured properly, skipping...")
            return
            
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
            # Fallback: Ghi vào file log
            with open('slack_failed_alerts.log', 'a') as f:
                f.write(f"{datetime.now()}: {json.dumps(payload)}\n")
            
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
    """Gửi alert test với format giống Zabbix"""
    test_alerts = [{
        'title': 'Free Memory--VIETTEL_PQ-WH_Slave.67',
        'status': 'firing',
        'severity': 'warning',
        'instance': 'VIETTEL_PQ-WH_Slave.67',
        'job': 'zabbix-server',
        'description': 'Team check lại hệ thống',
        'summary': 'Cánh báo Ram đang ở mức Warning',
        'value': 'B=14.44GB, C=1',
        'host': 'VIETTEL_PQ-WH_Slave.67',
        'item': 'Available memory',
        'item_key': 'vm.memory.size[available]',
        'grafana_folder': 'Zabbix-Server',
        'alertname': 'Free Memory--VIETTEL_PQ-WH_Slave.67'
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
    app.run(host='0.0.0.0', port=5000, debug=True), text, re.DOTALL)
    if annotations_section:
        annotations_text = annotations_section.group(1)
        annotation_matches = re.findall(r'-\s*(\w+)\s*=\s*(.+)', annotations_text)
        for key, value in annotation_matches:
            key = key.strip()
            value = value.strip()
            
            if key == 'description':
                data['description'] = value
            elif key == 'summary':
                data['summary'] = value
            else:
                data[key] = value

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
        # Tạm thời skip Slack nếu URL không hoạt động
        if not SLACK_WEBHOOK_URL or 'YOUR_' in SLACK_WEBHOOK_URL:
            logger.warning("Slack webhook URL not configured properly, skipping...")
            return
            
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
            # Fallback: Ghi vào file log
            with open('slack_failed_alerts.log', 'a') as f:
                f.write(f"{datetime.now()}: {json.dumps(payload)}\n")
            
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
        'instance': 'localhost:9090',
        'job': 'prometheus',
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
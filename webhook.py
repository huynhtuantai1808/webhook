from flask import Flask, request, jsonify
import requests
import re
import json
from datetime import datetime
import logging
import os

# ========== CONFIG ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

ALERT_EMOJI = {
    'firing': '🚨', 'resolved': '✅', 'critical': '💥',
    'warning': '⚠️', 'info': 'ℹ️', 'ok': '✅'
}

def format_value(raw_value, item_lower):
    try:
        float_val = float(raw_value)
        if 'memory' in item_lower:
            if float_val >= 1e9:
                return f"{float_val / 1e9:.2f} GB"
            elif float_val >= 1e6:
                return f"{float_val / 1e6:.2f} MB"
            elif float_val >= 1e3:
                return f"{float_val / 1e3:.2f} KB"
            else:
                return f"{float_val:.2f} B"
        elif 'cpu user time' in item_lower:
            return f"{float_val:.2f}%"
        else:
            return f"{float_val}"
    except:
        return raw_value

def extract_alert_info(data):
    alerts = []
    if 'alerts' in data:
        for alert in data['alerts']:
            if alert.get('labels', {}).get('alertname') == 'DatasourceNoData':
                continue

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
                'host': alert.get('labels', {}).get('host', 'N/A'),
                'item': alert.get('labels', {}).get('item', 'N/A'),
                'item_key': alert.get('labels', {}).get('item_key', 'N/A'),
                'grafana_folder': alert.get('labels', {}).get('grafana_folder', 'N/A'),
            }

            raw_value = str(alert_info['value'])
            item_lower = alert_info['item'].lower()

            if raw_value.startswith("B="):
                raw_value = raw_value.split(",")[0].replace("B=", "").strip()

            alert_info['value'] = format_value(raw_value, item_lower)

            if 'datasourceerror' in alert_info['summary'].lower() or 'datasourceerror' in alert_info['description'].lower():
                continue

            alerts.append(alert_info)
    elif 'message' in data:
        result = extract_alert_info_legacy(data['message'])
        if result:
            alerts.append(result)
    return alerts

def extract_alert_info_legacy(text):
    data = {
        'title': 'System Alert', 'status': 'firing', 'severity': 'warning',
        'instance': 'N/A', 'job': 'N/A', 'description': 'No description',
        'summary': 'No summary', 'value': 'N/A', 'host': 'N/A',
        'item': 'N/A', 'item_key': 'N/A', 'grafana_folder': 'N/A'
    }

    value_match = re.search(r'Value:\s*(.+?)(?=Labels:|$)', text, re.DOTALL)
    if value_match:
        value_text = value_match.group(1).strip()
        b_match = re.search(r'B=([0-9.eE+-]+)', value_text)
        item_lower = data['item'].lower()
        if b_match:
            raw_value = b_match.group(1)
            data['value'] = format_value(raw_value, item_lower)
        else:
            data['value'] = value_text

    labels_section = re.search(r'Labels:\s*(.+?)(?=Annotations:|$)', text, re.DOTALL)
    if labels_section:
        label_matches = re.findall(r'-\s*(\w+)\s*=\s*(.+)', labels_section.group(1))
        for key, value in label_matches:
            key, value = key.strip(), value.strip()
            data[key] = value
            if key == 'alertname':
                data['title'] = value
            elif key == 'host':
                data['instance'] = value

    annotations_section = re.search(r'Annotations:\s*(.+?)(?=$)', text, re.DOTALL)
    if annotations_section:
        annotation_matches = re.findall(r'-\s*(\w+)\s*=\s*(.+)', annotations_section.group(1))
        for key, value in annotation_matches:
            key, value = key.strip(), value.strip()
            data[key] = value

    if 'datasourceerror' in data['summary'].lower() or 'datasourceerror' in data['description'].lower():
        return None

    return data

def send_to_telegram(alerts):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram config missing, skipping...")
        return
    try:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": format_telegram_message(alerts),
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json=payload, timeout=10)
        if r.status_code == 200:
            logger.info("✅ Telegram alert sent.")
        else:
            logger.error(f"❌ Telegram failed: {r.status_code} - {r.text}")
    except Exception as e:
        logger.exception(f"Error sending to Telegram: {e}")

def send_to_slack(alerts):
    if not SLACK_WEBHOOK_URL:
        logger.warning("Slack webhook not set, skipping...")
        return
    try:
        payload = format_slack_message(alerts)
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=10)
        if r.status_code == 200:
            logger.info("✅ Slack alert sent.")
        else:
            logger.error(f"❌ Slack failed: {r.status_code} - {r.text}")
    except Exception as e:
        logger.exception(f"Error sending to Slack: {e}")

def format_telegram_message(alerts):
    messages = []
    for alert in alerts:
        emoji = ALERT_EMOJI.get(alert['status'].lower(), '🔔')
        severity_badge = {
            'critical': '🔴 CRITICAL', 'warning': '🟡 WARNING',
            'info': '🔵 INFO', 'ok': '🟢 OK'
        }.get(alert['severity'].lower(), alert['severity'].upper())
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
    return "\n".join(messages)

def format_slack_message(alerts):
    messages = []
    for alert in alerts:
        emoji = ALERT_EMOJI.get(alert['status'].lower(), '🔔')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
    return {"text": f"🚨 *System Alert Notification* ({len(alerts)} alert{'s' if len(alerts) > 1 else ''})\n" + "\n".join(messages)}

def send_test_alert():
    alert = {
        'title': 'Free Memory Alert',
        'status': 'firing',
        'severity': 'warning',
        'instance': 'localhost',
        'job': 'zabbix-server',
        'description': 'RAM usage high',
        'summary': 'Memory over 85%',
        'value': 'B=1.4449995776e+10, C=1',
        'host': 'localhost',
        'item': 'Available memory',
        'item_key': 'vm.memory.size[available]',
        'grafana_folder': 'Zabbix'
    }
    send_to_slack([alert])
    send_to_telegram([alert])

@app.route('/test', methods=['GET'])
def test_alert_route():
    send_test_alert()
    return jsonify({"status": "Test alert sent"}), 200

@app.route('/test-slack', methods=['GET'])
def test_slack_only():
    test_payload = {"text": "🚨 Test message from webhook"}
    r = requests.post(SLACK_WEBHOOK_URL, json=test_payload)
    return jsonify({
        "status": "ok" if r.status_code == 200 else "fail",
        "code": r.status_code,
        "text": r.text
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

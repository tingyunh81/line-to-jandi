import os
import hmac
import hashlib
import base64
import json
import requests
from flask import Flask, request, abort

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', '')
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')
JANDI_WEBHOOK_URL = os.environ.get('JANDI_WEBHOOK_URL', '')


def verify_signature(body: bytes, signature: str) -> bool:
    hash_digest = hmac.new(
        LINE_CHANNEL_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash_digest).decode('utf-8')
    return hmac.compare_digest(expected, signature)


def get_group_member_profile(group_id, user_id):
    url = f'https://api.line.me/v2/bot/group/{group_id}/member/{user_id}'
    headers = {'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def get_user_profile(user_id):
    url = f'https://api.line.me/v2/bot/profile/{user_id}'
    headers = {'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def send_to_jandi(sender_name, text, msg_type='text'):
    if msg_type == 'text':
        body = f'**{sender_name}** {text}'
    else:
        body = f'**{sender_name}** sent a {msg_type} message'
    payload = {'body': body, 'connectColor': '#00B900', 'connectInfo': [{'title': 'LINE Group', 'description': 'Auto-forwarded'}]}
    headers = {'Accept': 'application/vnd.tosslab.jandi-v2+json', 'Content-Type': 'application/json'}
    try:
        requests.post(JANDI_WEBHOOK_URL, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f'Error: {e}')


@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data()
    if not verify_signature(body, signature):
        abort(400)
    data = json.loads(body)
    for event in data.get('events', []):
        if event.get('type') != 'message':
            continue
        source = event.get('source', {})
        user_id = source.get('userId')
        source_type = source.get('type')
        sender_name = 'Unknown'
        if user_id:
            if source_type == 'group':
                profile = get_group_member_profile(source.get('groupId', ''), user_id)
            else:
                profile = get_user_profile(user_id)
            if profile:
                sender_name = profile.get('displayName', 'Unknown')
        message = event.get('message', {})
        send_to_jandi(sender_name, message.get('text', ''), message.get('type', 'text'))
    return 'OK'


@app.route('/', methods=['GET'])
def health():
    return 'LINE to Jandi relay running'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

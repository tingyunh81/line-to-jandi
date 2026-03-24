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


def get_group_member_profile(group_id: str, user_id: str) -> dict:
    url = f'https://api.line.me/v2/bot/group/{group_id}/member/{user_id}'
    headers = {'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        print(f'Group profile status: {resp.status_code}')
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f'Group profile error: {resp.text[:200]}')
    except Exception as e:
        print(f'Group profile exception: {e}')
    return {}


def get_user_profile(user_id: str) -> dict:
    url = f'https://api.line.me/v2/bot/profile/{user_id}'
    headers = {'Authorization': f'Bearer {LINE_CHANNEL_ACCESS_TOKEN}'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        print(f'User profile status: {resp.status_code}')
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f'User profile error: {resp.text[:200]}')
    except Exception as e:
        print(f'User profile exception: {e}')
    return {}


def send_to_jandi(sender_name: str, text: str, msg_type: str = 'text'):
    if msg_type == 'text':
        msg_body = text
        description = text
    elif msg_type == 'image':
        msg_body = 'sent an image'
        description = 'sent an image'
    elif msg_type == 'video':
        msg_body = 'sent a video'
        description = 'sent a video'
    elif msg_type == 'sticker':
        msg_body = 'sent a sticker'
        description = 'sent a sticker'
    else:
        msg_body = f'sent a {msg_type}'
        description = msg_body

    payload = {
        'body': f'[{sender_name}] {msg_body}',
        'connectColor': '#00B900',
        'connectInfo': [
            {
                'title': f'LINE > {sender_name}',
                'description': description
            }
        ]
    }

    headers = {
        'Accept': 'application/vnd.tosslab.jandi-v2+json',
        'Content-Type': 'application/json'
    }

    try:
        resp = requests.post(JANDI_WEBHOOK_URL, json=payload, headers=headers, timeout=10)
        print(f'Jandi response: {resp.status_code}')
    except Exception as e:
        print(f'Jandi error: {e}')


@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data()

    if not verify_signature(body, signature):
        print('Invalid signature')
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
                group_id = source.get('groupId', '')
                profile = get_group_member_profile(group_id, user_id)
            else:
                profile = get_user_profile(user_id)

            if profile:
                sender_name = profile.get('displayName', 'Unknown')
                print(f'Sender: {sender_name}')
            else:
                print(f'Profile fetch failed: user_id={user_id}, type={source_type}')

        message = event.get('message', {})
        msg_type = message.get('type', 'text')
        text = message.get('text', '')

        print(f'MSG type={msg_type} from={sender_name}: {text[:50]}')
        send_to_jandi(sender_name, text, msg_type)

    return 'OK'


@app.route('/', methods=['GET'])
def health():
    return 'LINE to Jandi relay running'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

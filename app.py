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

# Default Jandi Webhook (used for groups not in the mapping)
JANDI_WEBHOOK_URL = os.environ.get('JANDI_WEBHOOK_URL', '')

# Multi-group mapping
# Format: GROUP_WEBHOOK_MAP={"GroupId1":"https://jandi-url-1","GroupId2":"https://jandi-url-2"}
_GROUP_WEBHOOK_MAP = {}
_raw_map = os.environ.get('GROUP_WEBHOOK_MAP', '')
if _raw_map:
    try:
        _GROUP_WEBHOOK_MAP = json.loads(_raw_map)
        print(f'Loaded {len(_GROUP_WEBHOOK_MAP)} group webhook mappings')
    except Exception as e:
        print(f'Warning: GROUP_WEBHOOK_MAP parse error: {e}')


def get_jandi_url_for_group(group_id: str) -> str:
    if group_id in _GROUP_WEBHOOK_MAP:
        return _GROUP_WEBHOOK_MAP[group_id]
    return JANDI_WEBHOOK_URL


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


def send_to_jandi(jandi_url: str, sender_name: str, text: str,
                  msg_type: str = 'text', group_id: str = ''):
    if msg_type == 'text':
        msg_body = text
        description = text
    elif msg_type == 'image':
        msg_body = 'sent an image'
        description = msg_body
    elif msg_type == 'video':
        msg_body = 'sent a video'
        description = msg_body
    elif msg_type == 'audio':
        msg_body = 'sent an audio'
        description = msg_body
    elif msg_type == 'sticker':
        msg_body = 'sent a sticker'
        description = msg_body
    elif msg_type == 'file':
        msg_body = 'sent a file'
        description = msg_body
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
        resp = requests.post(jandi_url, json=payload, headers=headers, timeout=10)
        print(f'Jandi response: {resp.status_code} (group={group_id})')
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
        group_id = source.get('groupId', '') if source_type == 'group' else ''

        print(f'Incoming: source_type={source_type}, group_id={group_id}')

        sender_name = 'Unknown'
        if user_id:
            if source_type == 'group' and group_id:
                profile = get_group_member_profile(group_id, user_id)
            else:
                profile = get_user_profile(user_id)

            if profile:
                sender_name = profile.get('displayName', 'Unknown')
                print(f'Sender: {sender_name}')
            else:
                print(f'Profile fetch failed: user_id={user_id}')

        message = event.get('message', {})
        msg_type = message.get('type', 'text')
        text = message.get('text', '')

        jandi_url = get_jandi_url_for_group(group_id)
        if not jandi_url:
            print(f'No Jandi URL for group_id={group_id}, skipping')
            continue

        print(f'Forwarding: sender={sender_name}, type={msg_type}')
        send_to_jandi(jandi_url, sender_name, text, msg_type, group_id)

    return 'OK'


@app.route('/', methods=['GET'])
def health():
    n = len(_GROUP_WEBHOOK_MAP)
    return f'LINE to Jandi relay running ({n} group mappings loaded)'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

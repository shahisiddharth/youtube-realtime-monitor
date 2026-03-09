import os
import hmac
import hashlib
import requests
import xml.etree.ElementTree as ET
from flask import Flask, request, Response
from datetime import datetime, timedelta

app = Flask(__name__)

# ============================================================
# CONFIGURATION
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "mysecret123")

CHANNELS_TO_MONITOR = [
    "UCI0XKEplxvfqgoLht1mtb-A",   # FlickMatic HoTs
    "UCtOrMEFh-AS_F4Z0VXuVrPQ",   # Channel 2
    "UC9pp-0UMHx8tkxf52jslfKQ",   # Channel 3
    "UCGbL1HkQsVvQ-aYIRvxp8AQ",   # Channel 4
]

KEYWORDS = ["hindi dubbed", "hindi dub", "korean", "kdrama", "k-drama", "korean movie", "netflix", "hindi"]

# ============================================================
# SUBSCRIBE TO YOUTUBE CHANNELS
# ============================================================
def subscribe_to_channel(channel_id, callback_url):
    hub_url = "https://pubsubhubbub.appspot.com/subscribe"
    topic_url = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
    
    data = {
        "hub.callback": callback_url,
        "hub.topic": topic_url,
        "hub.verify": "async",
        "hub.mode": "subscribe",
        "hub.secret": WEBHOOK_SECRET,
        "hub.lease_seconds": 432000,  # 5 days
    }
    
    response = requests.post(hub_url, data=data)
    print(f"Subscribed to {channel_id}: {response.status_code}")
    return response.status_code

def subscribe_all(callback_url):
    for channel_id in CHANNELS_TO_MONITOR:
        subscribe_to_channel(channel_id, callback_url)

# ============================================================
# KEYWORD CHECK
# ============================================================
def is_relevant(title):
    title_lower = title.lower()
    return any(k.lower() in title_lower for k in KEYWORDS)

# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================
def send_telegram(video_id, title, channel_name, published):
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    
    try:
        pub_time = datetime.fromisoformat(published.replace('Z', '+00:00'))
        ist_time = pub_time + timedelta(hours=5, minutes=30)
        time_str = ist_time.strftime("%d %b %Y, %I:%M %p IST")
    except:
        time_str = published

    message = f"""🔔 *Naya Korean Hindi Dubbed Video!*

📺 *Channel:* {channel_name}
🎬 *Title:* {title}
🕐 *Time:* {time_str}

🔗 [Video Link]({video_url})

⚡ Jaldi daal apne channel pe!"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })
    print(f"✅ Notification sent: {title}")

# ============================================================
# WEBHOOK ROUTES
# ============================================================

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """YouTube hub verification"""
    challenge = request.args.get("hub.challenge", "")
    return Response(challenge, status=200)

@app.route("/webhook", methods=["POST"])
def receive_webhook():
    """Receive new video notifications from YouTube"""
    body = request.data
    
    try:
        root = ET.fromstring(body)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'yt': 'http://www.youtube.com/xml/schemas/2015'
        }
        
        entry = root.find('atom:entry', ns)
        if entry is None:
            return Response("OK", status=200)
        
        video_id = entry.find('yt:videoId', ns)
        title = entry.find('atom:title', ns)
        author = entry.find('atom:author/atom:name', ns)
        published = entry.find('atom:published', ns)
        
        if video_id is not None and title is not None:
            vid = video_id.text
            ttl = title.text
            channel = author.text if author is not None else "Unknown"
            pub = published.text if published is not None else ""
            
            print(f"New video: {ttl} from {channel}")
            
            if is_relevant(ttl):
                send_telegram(vid, ttl, channel, pub)
    
    except Exception as e:
        print(f"Error parsing webhook: {e}")
    
    return Response("OK", status=200)

@app.route("/subscribe", methods=["GET"])
def manual_subscribe():
    """Manually trigger subscription to all channels"""
    callback_url = request.url_root + "webhook"
    subscribe_all(callback_url)
    return f"Subscribed to {len(CHANNELS_TO_MONITOR)} channels! Callback: {callback_url}"

@app.route("/", methods=["GET"])
def home():
    return "🎬 YouTube Korean Hindi Dubbed Monitor - Running! Visit /subscribe to activate."

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

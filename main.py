import os
import requests
import xml.etree.ElementTree as ET
import threading
import time
from flask import Flask, request, Response
from datetime import datetime, timedelta

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "mysecret123")
RENDER_URL = "https://youtube-realtime-monitor.onrender.com"

CHANNELS_TO_MONITOR = [
    "UCI0XKEplxvfqgoLht1mtb-A",
    "UCtOrMEFh-AS_F4Z0VXuVrPQ",
    "UC9pp-0UMHx8tkxf52jslfKQ",
    "UCGbL1HkQsVvQ-aYIRvxp8AQ",
]

KEYWORDS = ["hindi dubbed", "hindi dub", "korean", "kdrama", "k-drama", "korean movie", "netflix", "hindi"]

def keep_alive():
    while True:
        time.sleep(14 * 60)
        try:
            requests.get(f"{RENDER_URL}/ping", timeout=10)
            print("✅ Self-ping - server awake!")
        except Exception as e:
            print(f"Ping error: {e}")

def auto_resubscribe():
    while True:
        time.sleep(4 * 24 * 60 * 60)
        try:
            subscribe_all(f"{RENDER_URL}/webhook")
            print("✅ Auto-resubscribed!")
        except Exception as e:
            print(f"Resubscribe error: {e}")

def subscribe_to_channel(channel_id, callback_url):
    hub_url = "https://pubsubhubbub.appspot.com/subscribe"
    topic_url = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
    data = {
        "hub.callback": callback_url,
        "hub.topic": topic_url,
        "hub.verify": "async",
        "hub.mode": "subscribe",
        "hub.secret": WEBHOOK_SECRET,
        "hub.lease_seconds": 432000,
    }
    response = requests.post(hub_url, data=data)
    print(f"Subscribed to {channel_id}: {response.status_code}")

def subscribe_all(callback_url):
    for channel_id in CHANNELS_TO_MONITOR:
        subscribe_to_channel(channel_id, callback_url)

def is_relevant(title):
    return any(k.lower() in title.lower() for k in KEYWORDS)

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

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    })
    print(f"✅ Notification sent: {title}")

@app.route("/ping", methods=["GET"])
def ping():
    return "pong", 200

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    challenge = request.args.get("hub.challenge", "")
    return Response(challenge, status=200)

@app.route("/webhook", methods=["POST"])
def receive_webhook():
    body = request.data
    try:
        root = ET.fromstring(body)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
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
            print(f"New video: {ttl}")
            if is_relevant(ttl):
                send_telegram(vid, ttl, channel, pub)
    except Exception as e:
        print(f"Error: {e}")
    return Response("OK", status=200)

@app.route("/subscribe", methods=["GET"])
def manual_subscribe():
    subscribe_all(f"{RENDER_URL}/webhook")
    return f"✅ Subscribed to {len(CHANNELS_TO_MONITOR)} channels!"

@app.route("/", methods=["GET"])
def home():
    return "🎬 YouTube Monitor - Running 24/7! Auto-ping active ✅"

# Start background threads
ping_thread = threading.Thread(target=keep_alive, daemon=True)
ping_thread.start()

resub_thread = threading.Thread(target=auto_resubscribe, daemon=True)
resub_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

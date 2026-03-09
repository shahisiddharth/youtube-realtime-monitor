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
COOKIES_FILE = "/opt/render/project/src/cookies.txt"

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

def send_telegram_with_buttons(video_id, title, channel_name, published):
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

🔗 [YouTube Link]({video_url})

⚡ Jaldi daal apne channel pe!"""

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🖼️ Thumbnail", "callback_data": f"dl_thumb_{video_id}"}
            ]
        ]
    }

    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": keyboard
    })
    print(f"✅ Notification sent: {title}")

def download_and_send_video(video_id, chat_id):
    from pytubefix import YouTube
    from pytubefix.cli import on_progress
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    send_status(chat_id, "⏳ Video download ho raha hai... thoda wait karo!")

    try:
        yt = YouTube(video_url, on_progress_callback=on_progress, use_oauth=False, allow_oauth_cache=False)
        title = yt.title

        # Get best MP4 stream under 50MB
        stream = yt.streams.filter(progressive=True, file_extension="mp4").order_by("resolution").last()
        if not stream:
            stream = yt.streams.filter(file_extension="mp4").order_by("resolution").first()

        if not stream:
            send_status(chat_id, "❌ Koi downloadable format nahi mila!")
            return

        filename = stream.download(output_path="/tmp", filename=f"{video_id}.mp4")

        file_size = os.path.getsize(filename)
        if file_size > 50 * 1024 * 1024:
            send_status(chat_id, "❌ Video bahut badi hai (50MB se zyada)!")
            os.remove(filename)
            return

        with open(filename, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
                data={"chat_id": chat_id, "caption": f"🎬 {title}"},
                files={"video": f}
            )
        os.remove(filename)
        print(f"✅ Video sent: {title}")

    except Exception as e:
        print(f"Video download error: {e}")
        send_status(chat_id, "❌ Video download nahi hua. YouTube se seedha download karo!")

def download_and_send_thumbnail(video_id, chat_id):
    send_status(chat_id, "⏳ Thumbnail download ho raha hai...")
    try:
        thumb_urls = [
            f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        ]
        thumb_data = None
        for thumb_url in thumb_urls:
            response = requests.get(thumb_url)
            if response.status_code == 200 and len(response.content) > 5000:
                thumb_data = response.content
                break

        if thumb_data:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                data={"chat_id": chat_id, "caption": "🖼️ Thumbnail"},
                files={"photo": ("thumbnail.jpg", thumb_data, "image/jpeg")}
            )
            print(f"✅ Thumbnail sent for {video_id}")
        else:
            send_status(chat_id, "❌ Thumbnail nahi mila!")
    except Exception as e:
        print(f"Thumbnail error: {e}")
        send_status(chat_id, "❌ Thumbnail download nahi hua!")

def send_status(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )

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
                send_telegram_with_buttons(vid, ttl, channel, pub)
    except Exception as e:
        print(f"Error: {e}")
    return Response("OK", status=200)

@app.route("/telegram_callback", methods=["POST"])
def telegram_callback():
    data = request.json
    if not data or "callback_query" not in data:
        return "OK", 200

    callback = data["callback_query"]
    callback_data = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
        json={"callback_query_id": callback["id"]}
    )

    if callback_data.startswith("dl_video_"):
        video_id = callback_data.replace("dl_video_", "")
        thread = threading.Thread(target=download_and_send_video, args=(video_id, chat_id))
        thread.daemon = True
        thread.start()

    elif callback_data.startswith("dl_thumb_"):
        video_id = callback_data.replace("dl_thumb_", "")
        thread = threading.Thread(target=download_and_send_thumbnail, args=(video_id, chat_id))
        thread.daemon = True
        thread.start()

    return "OK", 200

@app.route("/set_webhook", methods=["GET"])
def set_bot_webhook():
    webhook_url = f"{RENDER_URL}/telegram_callback"
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
        json={"url": webhook_url}
    )
    return f"Bot webhook set: {response.json()}"

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
    

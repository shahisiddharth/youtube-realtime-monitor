import os, requests, json, threading, time
import xml.etree.ElementTree as ET
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

# --- CONFIG ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ALL_CHAT_IDS = [TELEGRAM_CHAT_ID, "1420941229"]
WEBHOOK_SECRET = "mysecret123"
# Is URL ko apni asli Render URL se badal dein agar ye alag hai
RENDER_URL = "https://youtube-realtime-monitor-1.onrender.com"

CHANNELS_TO_MONITOR = [
    "UCI0XKEplxvfqgoLht1mtb-A",
    "UCtOrMEFh-AS_F4Z0VXuVrPQ",
    "UC9pp-0UMHx8tkxf52jslfKQ",
    "UCGbL1HkQsVvQ-aYIRvxp8AQ",
]
KEYWORDS = ["hindi dubbed", "hindi dub", "korean", "kdrama", "k-drama", "korean movie", "netflix", "hindi"]
DB_FILE = os.path.join(os.getcwd(), "videos_db.json")

# --- DATABASE LOGIC ---
def save_video_to_db(video_data):
    data = []
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
        except: data = []
    
    if not any(v['id'] == video_data['id'] for v in data):
        data.insert(0, video_data)
        with open(DB_FILE, "w") as f:
            json.dump(data[:50], f)
        print(f"✅ Saved to DB: {video_data['title']}")

# --- KEEP-ALIVE (Server ko jagaye rakhne ke liye) ---
def keep_alive():
    while True:
        # Render Free Tier 15 min mein sota hai, hum 10 min mein ping karenge
        time.sleep(10 * 60) 
        try:
            response = requests.get(f"{RENDER_URL}/ping")
            print(f"🚀 Self-Ping Success: {response.status_code}")
        except Exception as e:
            print(f"❌ Self-Ping Error: {e}")

# --- YOUTUBE SUBSCRIPTION LOGIC ---
def subscribe_all():
    hub_url = "https://pubsubhubbub.appspot.com/subscribe"
    for channel_id in CHANNELS_TO_MONITOR:
        topic_url = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
        data = {
            "hub.callback": f"{RENDER_URL}/webhook",
            "hub.topic": topic_url,
            "hub.verify": "async",
            "hub.mode": "subscribe",
            "hub.secret": WEBHOOK_SECRET,
            "hub.lease_seconds": 432000,
        }
        requests.post(hub_url, data=data)
    print("✅ Subscribed to all channels")

# --- ROUTES ---
@app.route("/")
def home():
    return "🎬 YouTube Monitor Pro - Status: Active & Awake ✅"

@app.route("/ping")
def ping():
    return "pong", 200

@app.route("/api/videos", methods=["GET"])
def get_videos():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    challenge = request.args.get("hub.challenge", "")
    return Response(challenge, status=200)

@app.route("/webhook", methods=["POST"])
def receive_webhook():
    try:
        root = ET.fromstring(request.data)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
        entry = root.find('atom:entry', ns)
        if entry is not None:
            v_id = entry.find('yt:videoId', ns).text
            title = entry.find('atom:title', ns).text
            if any(k.lower() in title.lower() for k in KEYWORDS):
                video_obj = {"id": v_id, "title": title, "time": str(time.time())}
                save_video_to_db(video_obj)
                
                # Telegram Notification
                for cid in ALL_CHAT_IDS:
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                                 json={"chat_id": cid, "text": f"🔔 *Naya Video Aaya!*\n\n🎬 {title}\n\nApp check karein!", "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Webhook Error: {e}")
    return "OK", 200

@app.route("/subscribe")
def manual_subscribe():
    subscribe_all()
    return "✅ Subscription Request Sent! Monitoring started."

# --- START BACKGROUND THREADS ---
# 1. Keep Alive Thread
threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

import os, requests, threading, time
import xml.etree.ElementTree as ET
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ALL_CHAT_IDS = [TELEGRAM_CHAT_ID, "1420941229"]
RENDER_URL = "https://youtube-realtime-monitor-1.onrender.com"
WEBHOOK_SECRET = "mysecret123"
VIDEO_LIST = []

CHANNELS_TO_MONITOR = [
    "UCI0XKEplxvfqgoLht1mtb-A", "UCtOrMEFh-AS_F4Z0VXuVrPQ",
    "UC9pp-0UMHx8tkxf52jslfKQ", "UCGbL1HkQsVvQ-aYIRvxp8AQ",
]
KEYWORDS = ["hindi dubbed", "hindi dub", "korean", "kdrama", "k-drama", "korean movie", "netflix", "hindi"]

COBALT_API = "https://api.cobalt.tools/"

def cobalt_get_link(v_id, quality="720"):
    """
    Cobalt.tools API se direct download URL lo.
    - Free, no API key, no bot detection
    - YouTube, Twitter, Instagram sab support karta hai
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "url": f"https://www.youtube.com/watch?v={v_id}",
        "videoQuality": quality,
        "filenameStyle": "basic",
        "downloadMode": "auto",
    }
    resp = requests.post(COBALT_API, json=payload, headers=headers, timeout=30)
    data = resp.json()

    status = data.get("status")

    if status == "tunnel" or status == "redirect":
        return data.get("url"), quality + "p"
    elif status == "picker":
        # Multiple streams available — pehla lo
        items = data.get("picker", [])
        if items:
            return items[0].get("url"), quality + "p"

    raise Exception(f"Cobalt error: {data.get('error', {}).get('code', str(data))}")


@app.route("/api/get_link/<v_id>")
def get_link(v_id):
    quality = request.args.get('quality', '720')
    try:
        url, label = cobalt_get_link(v_id, quality)
        if not url:
            return jsonify({"error": "URL nahi mila"}), 500
        return jsonify({"url": url, "title": v_id, "quality": label, "ext": "mp4"})
    except Exception as e:
        # Fallback: 360p try karo
        try:
            url, label = cobalt_get_link(v_id, "360")
            return jsonify({"url": url, "title": v_id, "quality": label, "ext": "mp4"})
        except Exception as e2:
            return jsonify({"error": str(e2)}), 500


@app.route("/api/formats/<v_id>")
def get_formats(v_id):
    """Quality options — Cobalt 3 qualities support karta hai"""
    return jsonify({
        "title": v_id,
        "formats": [
            {"label": "1080p MP4", "height": 1080},
            {"label": "720p MP4",  "height": 720},
            {"label": "360p MP4",  "height": 360},
        ]
    })


@app.route("/api/test_push/<v_id>")
def test_push(v_id):
    video_obj = {"id": v_id, "title": f"TEST VIDEO: {v_id}"}
    if not any(v['id'] == v_id for v in VIDEO_LIST):
        VIDEO_LIST.insert(0, video_obj)
        return f"SUCCESS! Pushed {v_id}. Refresh App!"
    return "Already in list."

@app.route("/api/videos", methods=["GET"])
def get_videos():
    return jsonify(VIDEO_LIST)

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    return Response(request.args.get("hub.challenge", ""), status=200)

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
                if not any(v['id'] == v_id for v in VIDEO_LIST):
                    VIDEO_LIST.insert(0, {"id": v_id, "title": title})
                    if len(VIDEO_LIST) > 50: VIDEO_LIST.pop()
                    for cid in ALL_CHAT_IDS:
                        requests.post(
                            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                            json={"chat_id": cid, "text": f"🔔 *Naya Video!*\n\n🎬 {title}\n\nApp check karo!", "parse_mode": "Markdown"}
                        )
    except: pass
    return "OK", 200

@app.route("/subscribe")
def manual_subscribe():
    for ch in CHANNELS_TO_MONITOR:
        topic = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={ch}"
        requests.post("https://pubsubhubbub.appspot.com/subscribe", data={
            "hub.callback": f"{RENDER_URL}/webhook", "hub.topic": topic,
            "hub.verify": "async", "hub.mode": "subscribe",
            "hub.lease_seconds": 432000, "hub.secret": WEBHOOK_SECRET
        })
    return "Subscriptions Synced!"

@app.route("/")
def home():
    return f"Monitor Live! Cache: {len(VIDEO_LIST)} videos | Powered by Cobalt API"

@app.route("/ping")
def ping(): return "pong", 200

def keep_alive():
    while True:
        time.sleep(10 * 60)
        try: requests.get(f"{RENDER_URL}/ping")
        except: pass

threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    

import os, requests, json, threading, time, yt_dlp
import xml.etree.ElementTree as ET
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ALL_CHAT_IDS = [TELEGRAM_CHAT_ID, "1420941229"]
RENDER_URL = "https://youtube-realtime-monitor-1.onrender.com"
COOKIES_FILE = "cookies.txt" 
WEBHOOK_SECRET = "mysecret123"

VIDEO_LIST = []

CHANNELS_TO_MONITOR = [
    "UCI0XKEplxvfqgoLht1mtb-A", "UCtOrMEFh-AS_F4Z0VXuVrPQ",
    "UC9pp-0UMHx8tkxf52jslfKQ", "UCGbL1HkQsVvQ-aYIRvxp8AQ",
]
KEYWORDS = ["hindi dubbed", "hindi dub", "korean", "kdrama", "k-drama", "korean movie", "netflix", "hindi"]

# --- API: MANUAL LINK EXTRACTOR (FAIL-PROOF) ---
@app.route("/api/get_link/<v_id>")
def get_link(v_id):
    # Hum 'format' remove kar rahe hain taaki error na aaye
    ydl_opts = {
        'cookiefile': COOKIES_FILE,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        }
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/watch?v={v_id}"
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            final_url = None
            
            # Logic: Dhoondho koi aisa format jisme Video aur Audio DONO hon
            # Priority 1: 720p (ext mp4)
            for f in formats:
                if f.get('height') == 720 and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    final_url = f.get('url')
                    break
            
            # Priority 2: 360p (ext mp4)
            if not final_url:
                for f in formats:
                    if f.get('height') == 360 and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        final_url = f.get('url')
                        break
            
            # Priority 3: Koi bhi format jisme audio+video ho
            if not final_url:
                for f in reversed(formats): # Ulta check karein taaki best quality mile
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                        final_url = f.get('url')
                        break
            
            # Aakhri koshish: Pehla working link
            if not final_url:
                final_url = formats[0].get('url')

            return jsonify({
                "url": final_url, 
                "title": info.get('title', 'video'),
                "ext": 'mp4'
            })
    except Exception as e:
        return jsonify({"error": f"Extraction Error: {str(e)}"}), 500

# --- REST OF THE CODE ---
@app.route("/api/test_push/<v_id>")
def test_push(v_id):
    video_obj = {"id": v_id, "title": f"TEST VIDEO: {v_id}"}
    if not any(v['id'] == v_id for v in VIDEO_LIST):
        VIDEO_LIST.insert(0, video_obj)
        return f"✅ SUCCESS! Pushed {v_id}. Refresh App!"
    return "❌ Already in list."

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
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", 
                                     json={"chat_id": cid, "text": f"🔔 *Naya Video Aaya!*\n\n🎬 {title}\n\nApp check karein!", "parse_mode": "Markdown"})
    except: pass
    return "OK", 200

@app.route("/subscribe")
def manual_subscribe():
    for ch in CHANNELS_TO_MONITOR:
        topic = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={ch}"
        requests.post("https://pubsubhubbub.appspot.com/subscribe", data={
            "hub.callback": f"{RENDER_URL}/webhook", "hub.topic": topic,
            "hub.verify": "async", "hub.mode": "subscribe", "hub.lease_seconds": 432000, "hub.secret": WEBHOOK_SECRET
        })
    return "✅ Subscriptions Synced!"

@app.route("/")
def home():
    c_status = "Found ✅" if os.path.exists(COOKIES_FILE) else "Missing ❌"
    return f"🎬 Monitor Live! Cache: {len(VIDEO_LIST)} | Cookies: {c_status}"

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

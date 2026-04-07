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

# --- API: SMART LINK EXTRACTOR (PRO FALLBACK VERSION) ---
@app.route("/api/get_link/<v_id>")
def get_link(v_id):
    if not os.path.exists(COOKIES_FILE):
        return jsonify({"error": "Cookies file missing!"}), 500

    ydl_opts = {
        'cookiefile': COOKIES_FILE,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        # ✅ FIX: Best muxed formats priority (18=360p, 22=720p)
        'format': '18/22/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'skip': ['hls', 'dash']
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.ios.youtube/19.29.1 CFNetwork/1474 Darwin/23.0.0',
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/watch?v={v_id}"
            info = ydl.extract_info(url, download=False)
            
            # yt-dlp automatically picks the best URL based on 'format' string
            final_url = info.get('url')

            # Fallback Loop: Agar direct link nahi mila, toh formats scan karein
            if not final_url:
                formats = info.get('formats', [])
                for f in reversed(formats):
                    # Check for combined video and audio (Muxed)
                    if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url'):
                        final_url = f['url']
                        break
                
                # Ultimate Fallback: Just give any working URL
                if not final_url and formats:
                    final_url = formats[-1].get('url')

            if not final_url:
                return jsonify({"error": "No working link found for this video."}), 500

            return jsonify({
                "url": final_url, 
                "title": info.get('title', 'video'),
                "ext": 'mp4'
            })
    except Exception as e:
        return jsonify({"error": f"Extraction Error: {str(e)}"}), 500

# --- ROUTES ---
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
    return f"🎬 Hybrid Monitor Live! Cache: {len(VIDEO_LIST)} | Cookies: {c_status}"

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

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

# --- CORE HELPER: Best Muxed URL Extractor (No FFmpeg needed) ---
def extract_muxed_url(v_id):
    """
    Priority Chain (FFmpeg bilkul nahi chahiye):
    1. Format 22 -> 720p MP4 muxed (video+audio ek file)
    2. Format 18 -> 360p MP4 muxed (video+audio ek file)
    3. Any muxed -> jo bhi mila video+audio saath
    4. Last resort -> koi bhi pehla format
    """
    ydl_opts = {
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.ios.youtube/19.29.1 CFNetwork/1474 Darwin/23.0.0',
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={v_id}",
            download=False
        )

    formats = info.get('formats', [])
    title = info.get('title', 'video')

    # Step 1: Format 22 dhoondo (720p muxed mp4)
    for f in formats:
        if f.get('format_id') == '22' and f.get('url'):
            return f['url'], title, '720p'

    # Step 2: Format 18 dhoondo (360p muxed mp4)
    for f in formats:
        if f.get('format_id') == '18' and f.get('url'):
            return f['url'], title, '360p'

    # Step 3: Koi bhi muxed format (video+audio dono saath)
    for f in reversed(formats):
        has_video = f.get('vcodec', 'none') != 'none'
        has_audio = f.get('acodec', 'none') != 'none'
        if has_video and has_audio and f.get('url'):
            return f['url'], title, f.get('format_id', 'muxed')

    # Step 4: Last resort
    for f in formats:
        if f.get('url'):
            return f['url'], title, 'fallback'

    return None, title, None

# --- API: DOWNLOAD LINK ---
@app.route("/api/get_link/<v_id>")
def get_link(v_id):
    if not os.path.exists(COOKIES_FILE):
        return jsonify({"error": "Cookies file missing on server!"}), 500
    try:
        url, title, quality = extract_muxed_url(v_id)
        if not url:
            return jsonify({"error": "No downloadable format found."}), 500
        return jsonify({"url": url, "title": title, "quality": quality, "ext": "mp4"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- DEBUG: List all formats ---
@app.route("/api/debug/<v_id>")
def debug_formats(v_id):
    ydl_opts = {
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'quiet': True,
        'extractor_args': {'youtube': {'player_client': ['ios', 'android', 'web']}},
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
            formats = info.get('formats', [])
            result = []
            for f in formats:
                result.append({
                    "format_id": f.get('format_id'),
                    "ext": f.get('ext'),
                    "vcodec": f.get('vcodec'),
                    "acodec": f.get('acodec'),
                    "height": f.get('height'),
                    "has_url": bool(f.get('url'))
                })
            return jsonify({"total": len(result), "formats": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- UPDATE yt-dlp ---
@app.route("/api/update_ytdlp")
def update_ytdlp():
    import subprocess, importlib
    result = subprocess.run(["pip", "install", "--upgrade", "yt-dlp"], capture_output=True, text=True)
    importlib.reload(yt_dlp)
    return jsonify({"stdout": result.stdout[-500:], "version": yt_dlp.version.__version__})

# --- REST OF THE ROUTES ---
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
                            json={"chat_id": cid, "text": f"Naya Video Aaya!\n\n{title}\n\nApp check karein!", "parse_mode": "Markdown"}
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
    c_status = "Found" if os.path.exists(COOKIES_FILE) else "Missing"
    return f"Monitor Live! Cache: {len(VIDEO_LIST)} | Cookies: {c_status}"

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
    

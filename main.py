import os, requests, threading, time, yt_dlp
import xml.etree.ElementTree as ET
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

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

def get_all_muxed_formats(v_id):
    """
    Sirf muxed formats return karta hai - NO ffmpeg needed.
    Format 22 = 720p mp4, Format 18 = 360p mp4
    """
    ydl_opts = {
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        # KEY FIX: format specify mat karo, sab formats lo manually
        'format': 'best',
        'extractor_args': {'youtube': {'player_client': ['ios', 'web']}},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)

    title = info.get('title', 'video')
    formats = info.get('formats', [])

    # Sirf muxed formats (video+audio dono ek file mein)
    muxed = []
    for f in formats:
        has_v = f.get('vcodec', 'none') not in ('none', None)
        has_a = f.get('acodec', 'none') not in ('none', None)
        url = f.get('url')
        if has_v and has_a and url:
            muxed.append({
                'format_id': f.get('format_id'),
                'ext': f.get('ext', 'mp4'),
                'height': f.get('height', 0) or 0,
                'url': url,
                'label': f"{f.get('height', '?')}p {f.get('ext','mp4').upper()}"
            })

    # Height ke hisab se sort karo (highest first)
    muxed.sort(key=lambda x: x['height'], reverse=True)
    return title, muxed


@app.route("/api/get_link/<v_id>")
def get_link(v_id):
    """Default: best available muxed format"""
    quality = request.args.get('quality', 'best')  # ?quality=720 ya ?quality=360
    try:
        title, muxed = get_all_muxed_formats(v_id)
        if not muxed:
            return jsonify({"error": "Koi bhi downloadable format nahi mila!"}), 500

        chosen = muxed[0]  # default: best (highest)

        if quality == '720':
            for f in muxed:
                if f['height'] == 720: chosen = f; break
        elif quality == '360':
            for f in muxed:
                if f['height'] == 360: chosen = f; break
        elif quality == 'worst':
            chosen = muxed[-1]

        return jsonify({
            "url": chosen['url'],
            "title": title,
            "quality": chosen['label'],
            "ext": chosen['ext']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/formats/<v_id>")
def get_formats(v_id):
    """Sabhi available muxed formats return karo"""
    try:
        title, muxed = get_all_muxed_formats(v_id)
        return jsonify({
            "title": title,
            "formats": [{"label": f['label'], "height": f['height'], "format_id": f['format_id']} for f in muxed]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    

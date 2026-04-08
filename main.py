import os, requests, threading, time
import xml.etree.ElementTree as ET
from flask import Flask, request, Response, jsonify
from pytubefix import YouTube
from pytubefix.cli import on_progress

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


def get_yt_streams(v_id):
    """
    pytubefix se progressive (muxed) streams lo.
    Progressive = video+audio ek hi file — NO ffmpeg needed!
    """
    yt = YouTube(
        f"https://www.youtube.com/watch?v={v_id}",
        use_oauth=False,
        allow_oauth_cache=False,
        use_po_token=False,
    )
    # Progressive streams = muxed (720p ya 360p mp4)
    streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
    return yt.title, streams


@app.route("/api/formats/<v_id>")
def get_formats(v_id):
    """Sabhi available muxed formats return karo"""
    try:
        title, streams = get_yt_streams(v_id)
        formats = []
        for s in streams:
            formats.append({
                "itag": s.itag,
                "label": s.resolution or "unknown",
                "height": int(s.resolution.replace('p','')) if s.resolution else 0,
                "mime_type": s.mime_type,
                "url": s.url
            })
        return jsonify({"title": title, "formats": formats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/get_link/<v_id>")
def get_link(v_id):
    """Best ya selected quality ka direct URL do"""
    quality = request.args.get('quality', 'best')
    try:
        title, streams = get_yt_streams(v_id)
        stream_list = list(streams)

        if not stream_list:
            return jsonify({"error": "Koi bhi stream nahi mila!"}), 500

        chosen = stream_list[0]  # default: best (highest resolution first)

        if quality != 'best':
            for s in stream_list:
                if s.resolution == f"{quality}p":
                    chosen = s
                    break

        return jsonify({
            "url": chosen.url,
            "title": title,
            "quality": chosen.resolution,
            "ext": "mp4"
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
    return f"Monitor Live! Cache: {len(VIDEO_LIST)} videos"

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
    

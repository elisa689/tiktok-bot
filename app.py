import os
import re
import json
import hmac
import hashlib
import time
import requests
import yt_dlp
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Notion database IDs (one per slash command) ──────────────────────────────
NOTION_DB_MAP = {
    "competitor": os.getenv("NOTION_DB_COMPETITOR", "2fe5fe0ecdf64e1395ac2724cd5d1815"),
    "creators":   os.getenv("NOTION_DB_CREATORS",   "81113f55124246f8acb53bce3fa65f0e"),
    "internal":   os.getenv("NOTION_DB_INTERNAL",   "36c46d02fdb24e239074f3156ffca0e2"),
    "inspo":      os.getenv("NOTION_DB_INSPO",       "4c454905ada24c359aaaa1945a4f6e79"),
}

NOTION_TOKEN     = os.getenv("NOTION_TOKEN")
SLACK_SECRET     = os.getenv("SLACK_SIGNING_SECRET")
NOTION_VERSION   = "2022-06-28"

TIKTOK_URL_RE = re.compile(
    r"https?://(?:www\.|vm\.|vt\.)?tiktok\.com/[^\s>]+"
)


# ── Slack request verification ────────────────────────────────────────────────
def verify_slack_signature(req) -> bool:
    ts = req.headers.get("X-Slack-Request-Timestamp", "")
    sig = req.headers.get("X-Slack-Signature", "")
    if abs(time.time() - int(ts)) > 60 * 5:
        return False
    body = req.get_data(as_text=True)
    basestring = f"v0:{ts}:{body}"
    expected = "v0=" + hmac.new(
        SLACK_SECRET.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


# ── TikTok scraping via yt-dlp ────────────────────────────────────────────────
def scrape_tiktok(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "subtitleslangs": ["en"],
        "extractor_args": {"tiktok": {"app_version": []}},
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    username    = info.get("uploader_id") or info.get("uploader") or ""
    views       = info.get("view_count") or 0
    likes       = info.get("like_count") or 0
    comments    = info.get("comment_count") or 0
    shares      = info.get("repost_count") or 0
    title       = info.get("title") or info.get("description") or username

    engagement  = f"Likes: {likes:,}  Comments: {comments:,}  Shares: {shares:,}"

    # Transcript: pull from automatic captions if available
    transcript = ""
    auto_captions = info.get("automatic_captions") or {}
    subs = info.get("subtitles") or {}
    for lang_dict in [subs, auto_captions]:
        for lang, tracks in lang_dict.items():
            if "en" in lang:
                for track in tracks:
                    if track.get("ext") == "json3":
                        try:
                            r = requests.get(track["url"], timeout=10)
                            data = r.json()
                            transcript = " ".join(
                                e.get("utf8", "")
                                for event in data.get("events", [])
                                for e in event.get("segs", [])
                            ).strip()
                        except Exception:
                            pass
                        break
            if transcript:
                break
        if transcript:
            break

    return {
        "title":      title,
        "username":   username,
        "url":        url,
        "views":      views,
        "engagement": engagement,
        "transcript": transcript or "(no transcript available)",
    }


# ── Notion: add a row ─────────────────────────────────────────────────────────
def add_to_notion(database_id: str, data: dict):
    headers = {
        "Authorization":  f"Bearer {NOTION_TOKEN}",
        "Content-Type":   "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name":       {"title":     [{"text": {"content": data["title"]}}]},
            "Username":   {"rich_text": [{"text": {"content": data["username"]}}]},
            "TikTok URL": {"url":        data["url"]},
            "Views":      {"number":     data["views"]},
            "Engagement": {"rich_text": [{"text": {"content": data["engagement"]}}]},
            "Transcript": {"rich_text": [{"text": {"content": data["transcript"][:2000]}}]},
        },
    }
    resp = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Generic slash command handler ─────────────────────────────────────────────
def handle_command(command_name: str, req):
    if not verify_slack_signature(req):
        return jsonify({"text": "⛔ Invalid request signature."}), 403

    text = req.form.get("text", "").strip()
    url_match = TIKTOK_URL_RE.search(text)

    if not url_match:
        return jsonify({
            "response_type": "ephemeral",
            "text": f"Please include a TikTok URL.  Usage: `/{command_name} https://tiktok.com/...`"
        })

    tiktok_url  = url_match.group(0)
    db_id       = NOTION_DB_MAP[command_name]
    user_name   = req.form.get("user_name", "someone")

    # Acknowledge immediately (Slack requires <3s response)
    # In production, offload to a background task/queue
    try:
        data        = scrape_tiktok(tiktok_url)
        notion_page = add_to_notion(db_id, data)
        notion_url  = notion_page.get("url", "")

        return jsonify({
            "response_type": "in_channel",
            "text": (
                f"✅ *{user_name}* added a TikTok to *{command_name.capitalize()}*\n"
                f">*@{data['username']}* — {data['views']:,} views\n"
                f">{data['engagement']}\n"
                f"><{tiktok_url}|View on TikTok>  ·  <{notion_url}|Open in Notion>"
            ),
        })
    except Exception as e:
        return jsonify({
            "response_type": "ephemeral",
            "text": f"❌ Failed to process that link: {e}",
        })


# ── Routes (one per slash command) ────────────────────────────────────────────
@app.route("/competitor", methods=["POST"])
def competitor():
    return handle_command("competitor", request)

@app.route("/creators", methods=["POST"])
def creators():
    return handle_command("creators", request)

@app.route("/internal", methods=["POST"])
def internal():
    return handle_command("internal", request)

@app.route("/inspo", methods=["POST"])
def inspo():
    return handle_command("inspo", request)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

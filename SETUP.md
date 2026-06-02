# TikTok → Slack → Notion Setup Guide

## What this does
Post a TikTok URL with a slash command in Slack and it automatically extracts the username, views, engagement, and transcript, then adds a row to the matching Notion database.

| Command | Notion Database |
|---|---|
| `/competitor <url>` | Competitor Tracking |
| `/creators <url>` | Creators |
| `/internal <url>` | Internal |
| `/inspo <url>` | Inspo |

---

## Step 1 — Get your Notion token

1. Go to https://www.notion.so/profile/integrations
2. Click **New integration** → give it a name (e.g. "TikTok Bot")
3. Copy the **Internal Integration Token** (starts with `secret_`)
4. Open each of the 4 databases in Notion → click `...` → **Add connections** → select your integration

---

## Step 2 — Create your Slack app

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Under **Slash Commands**, create 4 commands:

   | Command | Request URL |
   |---|---|
   | `/competitor` | `https://YOUR-DOMAIN/competitor` |
   | `/creators` | `https://YOUR-DOMAIN/creators` |
   | `/internal` | `https://YOUR-DOMAIN/internal` |
   | `/inspo` | `https://YOUR-DOMAIN/inspo` |

3. Under **Basic Information** → copy your **Signing Secret**
4. Under **OAuth & Permissions** → install the app to your workspace

---

## Step 3 — Deploy to Railway (free tier)

1. Push this project to a GitHub repo
2. Go to https://railway.app → **New Project** → **Deploy from GitHub**
3. Add environment variables (from `.env.example`) in Railway's Variables tab
4. Railway gives you a public URL — paste it as the base for your Slack slash command URLs above

Or run locally with [ngrok](https://ngrok.com) for testing:
```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your values
python app.py
# in another terminal:
ngrok http 3000
```
Use the ngrok URL as your Slack request URL.

---

## Step 4 — Test it

In any Slack channel:
```
/competitor https://www.tiktok.com/@username/video/123456789
```

You should see a confirmation message with views, engagement, and a link to the new Notion row.

---

## Notes

- **Transcripts** are pulled from TikTok's auto-generated captions via yt-dlp. Not all videos have them.
- **Engagement** is formatted as `Likes / Comments / Shares`.
- Slack requires a response within 3 seconds. For slow TikTok pages, consider adding a background task queue (e.g. Redis + RQ) — the code is structured to make that easy.

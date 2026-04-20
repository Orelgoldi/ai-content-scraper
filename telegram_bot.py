"""
Telegram Bot - Interactive Content Browser
Sends scraped posts and lets you browse/filter via inline buttons.
"""

import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    os.system("pip install requests --break-system-packages -q")
    import requests

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "data" / "posts.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_db():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, text, parse_mode="Markdown", reply_markup=None):
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            resp = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            print(f"Error: {e}")
            return None

    def send_photo(self, photo_url, caption=""):
        try:
            resp = requests.post(f"{self.base_url}/sendPhoto", json={
                "chat_id": self.chat_id,
                "photo": photo_url,
                "caption": caption[:1024],
                "parse_mode": "Markdown",
            }, timeout=15)
            return resp.json()
        except Exception as e:
            print(f"Error sending photo: {e}")
            return None

    def send_post(self, post, category_name):
        """Send a single post as a rich Telegram message."""
        platform_emoji = {
            "instagram": "\U0001f4f8",
            "linkedin": "\U0001f4bc",
            "tiktok": "\U0001f3b5"
        }.get(post["platform"], "\U0001f4cc")

        text_preview = (post.get("text", "") or "")[:500]
        if len(post.get("text", "") or "") > 500:
            text_preview += "..."

        stats = f"\u2764\ufe0f {post.get('likes', 0):,}  \U0001f4ac {post.get('comments', 0):,}"
        if post.get("views"):
            stats += f"  \U0001f441 {post.get('views', 0):,}"

        message = f"""{platform_emoji} *{category_name}*

\U0001f464 *{post.get('author_name') or post.get('author', 'Unknown')}*
{post['platform'].title()} | {stats}

{text_preview}"""

        # Hebrew version if available
        if post.get("hebrew_text"):
            message += f"""

\U0001f1ee\U0001f1f1 *\u05d2\u05e8\u05e1\u05d4 \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea:*
{post['hebrew_text'][:400]}"""

        buttons = {"inline_keyboard": [
            [{"text": "\U0001f517 \u05e6\u05e4\u05d4 \u05d1\u05e4\u05d5\u05e1\u05d8", "url": post.get("url", "#")}],
        ]}

        if post.get("author_url"):
            buttons["inline_keyboard"].append(
                [{"text": f"\U0001f464 \u05e4\u05e8\u05d5\u05e4\u05d9\u05dc {post.get('author', '')}", "url": post["author_url"]}]
            )

        # Send with image if available
        if post.get("image_url"):
            self.send_photo(post["image_url"], caption=message[:1024])
        else:
            self.send_message(message, reply_markup=buttons)

    def send_daily_digest(self, posts, config):
        """Send a daily digest of top posts."""
        if not posts:
            self.send_message("\U0001f4ed *\u05d0\u05d9\u05df \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd \u05d7\u05d3\u05e9\u05d9\u05dd \u05d4\u05d9\u05d5\u05dd*")
            return

        # Sort by likes
        top_posts = sorted(posts, key=lambda p: p.get("likes", 0), reverse=True)[:5]

        header = f"""\U0001f4ca *\u05e1\u05d9\u05db\u05d5\u05dd \u05d9\u05d5\u05de\u05d9 - AI Content Scraper*

\U0001f4e6 \u05e1\u05d4"\u05db \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd \u05d7\u05d3\u05e9\u05d9\u05dd: *{len(posts)}*
\u2b50 Top 5 \u05dc\u05e4\u05d9 \u05dc\u05d9\u05d9\u05e7\u05d9\u05dd:
"""
        self.send_message(header)

        for i, post in enumerate(top_posts, 1):
            category_name = next(
                (c["name_he"] for c in config["categories"] if c["id"] == post.get("category")),
                "\u05db\u05dc\u05dc\u05d9"
            )
            self.send_post(post, f"#{i} {category_name}")

    def send_category_report(self, posts, config):
        """Send a breakdown by category."""
        cats = {}
        for p in posts:
            cat = p.get("category", "other")
            if cat not in cats:
                cats[cat] = []
            cats[cat].append(p)

        message = "\U0001f3f7\ufe0f *\u05e4\u05d9\u05dc\u05d5\u05d7 \u05dc\u05e4\u05d9 \u05e7\u05d8\u05d2\u05d5\u05e8\u05d9\u05d5\u05ea:*\n\n"
        for cat_config in config["categories"]:
            cat_posts = cats.get(cat_config["id"], [])
            total_likes = sum(p.get("likes", 0) for p in cat_posts)
            message += f"\u2022 *{cat_config['name_he']}*: {len(cat_posts)} \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd | {total_likes:,} \u05dc\u05d9\u05d9\u05e7\u05d9\u05dd\n"

        self.send_message(message)


def main():
    config = load_config()
    db = load_db()

    # Override config with environment variables (Railway)
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        config["telegram"]["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    if os.environ.get("TELEGRAM_CHAT_ID"):
        config["telegram"]["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]

    token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]

    if token == "YOUR_TELEGRAM_BOT_TOKEN":
        print("\u274c Please set your Telegram bot token in config.json or TELEGRAM_BOT_TOKEN env var")
        return

    bot = TelegramBot(token, chat_id)
    posts = db.get("posts", [])

    # Parse command
    command = sys.argv[1] if len(sys.argv) > 1 else "digest"

    if command == "digest":
        # Send daily digest of newest posts (last 24h)
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=24)
        recent = [p for p in posts if p.get("scraped_at", "") > cutoff.isoformat()]
        bot.send_daily_digest(recent or posts[:10], config)

    elif command == "categories":
        bot.send_category_report(posts, config)

    elif command == "top":
        # Send top 5 all-time posts
        top = sorted(posts, key=lambda p: p.get("likes", 0), reverse=True)[:5]
        bot.send_message("\U0001f3c6 *Top 5 \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd \u05dc\u05e4\u05d9 \u05dc\u05d9\u05d9\u05e7\u05d9\u05dd:*")
        for i, post in enumerate(top, 1):
            cat_name = next((c["name_he"] for c in config["categories"] if c["id"] == post.get("category")), "\u05db\u05dc\u05dc\u05d9")
            bot.send_post(post, f"#{i} {cat_name}")

    elif command == "hebrew":
        # Send posts that have Hebrew translations
        hebrew_posts = [p for p in posts if p.get("hebrew_status") == "done"][:5]
        if hebrew_posts:
            bot.send_message(f"\U0001f1ee\U0001f1f1 *{len(hebrew_posts)} \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd \u05e2\u05dd \u05ea\u05e8\u05d2\u05d5\u05dd \u05dc\u05e2\u05d1\u05e8\u05d9\u05ea:*")
            for post in hebrew_posts:
                cat_name = next((c["name_he"] for c in config["categories"] if c["id"] == post.get("category")), "\u05db\u05dc\u05dc\u05d9")
                bot.send_post(post, cat_name)
        else:
            bot.send_message("\u274c \u05d0\u05d9\u05df \u05e4\u05d5\u05e1\u05d8\u05d9\u05dd \u05de\u05ea\u05d5\u05e8\u05d2\u05de\u05d9\u05dd \u05e2\u05d3\u05d9\u05d9\u05df")

    else:
        print(f"Usage: python telegram_bot.py [digest|categories|top|hebrew]")


if __name__ == "__main__":
    main()

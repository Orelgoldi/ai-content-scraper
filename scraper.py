"""
AI Content Scraper - Apify Integration
Scrapes Instagram, LinkedIn & TikTok for AI/GenAI design content.
Categorizes posts, saves to JSON DB, and sends Telegram notifications.
"""

import json
import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path

try:
    from apify_client import ApifyClient
except ImportError:
    print("Installing apify-client...")
    os.system("pip install apify-client --break-system-packages -q")
    from apify_client import ApifyClient

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system("pip install requests --break-system-packages -q")
    import requests


# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "data" / "posts.json"
IMAGES_DIR = BASE_DIR / "data" / "images"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_db():
    if DB_PATH.exists():
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"posts": [], "last_run": None, "stats": {"total": 0, "by_platform": {}, "by_category": {}}}


def save_db(db):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def generate_post_id(post):
    raw = f"{post.get('platform','')}-{post.get('url','')}-{post.get('text','')[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()


# ─── Category Classification ────────────────────────────────────────────────
def classify_post(text, config):
    text_lower = (text or "").lower()
    scores = {}

    for cat in config["categories"]:
        score = sum(1 for kw in cat["keywords"] if kw.lower() in text_lower)
        if score > 0:
            scores[cat["id"]] = score

    if not scores:
        return "trends"  # default category

    return max(scores, key=scores.get)


# ─── Image Downloader ───────────────────────────────────────────────────────
def download_image(url, post_id):
    if not url:
        return None
    try:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        ext = ".jpg"
        if ".png" in url:
            ext = ".png"
        elif ".webp" in url:
            ext = ".webp"
        filepath = IMAGES_DIR / f"{post_id}{ext}"
        if filepath.exists():
            return str(filepath)
        resp = requests.get(url, timeout=15, stream=True)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return str(filepath)
    except Exception as e:
        print(f"  ⚠ Image download failed: {e}")
        return None


# ─── Instagram Scraper ───────────────────────────────────────────────────────
def scrape_instagram(client, config):
    print("\n📸 Scraping Instagram...")
    posts = []
    scraping_config = config["scraping"]

    # Scrape by hashtags
    run_input = {
        "directUrls": [f"https://www.instagram.com/explore/tags/{tag.strip('#')}/"
                       for tag in scraping_config["hashtags_instagram"][:5]],
        "resultsLimit": scraping_config["max_posts_per_run"],
        "resultsType": "posts",
        "searchType": "hashtag",
    }

    try:
        actor = config["apify"]["actors"]["instagram"]
        run = client.actor(actor).call(run_input=run_input)
        dataset = client.dataset(run["defaultDatasetId"])

        for item in dataset.iterate_items():
            post = {
                "platform": "instagram",
                "author": item.get("ownerUsername", ""),
                "author_name": item.get("ownerFullName", ""),
                "author_url": f"https://instagram.com/{item.get('ownerUsername', '')}",
                "author_followers": item.get("ownerFollowerCount", 0),
                "text": item.get("caption", ""),
                "url": item.get("url", ""),
                "image_url": item.get("displayUrl", ""),
                "video_url": item.get("videoUrl", ""),
                "likes": item.get("likesCount", 0),
                "comments": item.get("commentsCount", 0),
                "timestamp": item.get("timestamp", ""),
                "hashtags": item.get("hashtags", []),
                "type": item.get("type", "image"),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            post["id"] = generate_post_id(post)
            posts.append(post)
            print(f"  ✓ @{post['author']} - {post['likes']} likes")

    except Exception as e:
        print(f"  ✗ Instagram error: {e}")

    # Scrape specific profiles
    for profile in scraping_config["profiles_to_track"].get("instagram", []):
        try:
            profile_input = {
                "directUrls": [f"https://www.instagram.com/{profile}/"],
                "resultsLimit": 10,
                "resultsType": "posts",
            }
            run = client.actor(actor).call(run_input=profile_input)
            dataset = client.dataset(run["defaultDatasetId"])
            for item in dataset.iterate_items():
                post = {
                    "platform": "instagram",
                    "author": item.get("ownerUsername", profile),
                    "author_name": item.get("ownerFullName", ""),
                    "author_url": f"https://instagram.com/{profile}",
                    "author_followers": item.get("ownerFollowerCount", 0),
                    "text": item.get("caption", ""),
                    "url": item.get("url", ""),
                    "image_url": item.get("displayUrl", ""),
                    "video_url": item.get("videoUrl", ""),
                    "likes": item.get("likesCount", 0),
                    "comments": item.get("commentsCount", 0),
                    "timestamp": item.get("timestamp", ""),
                    "hashtags": item.get("hashtags", []),
                    "type": item.get("type", "image"),
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                post["id"] = generate_post_id(post)
                posts.append(post)
        except Exception as e:
            print(f"  ✗ Profile {profile} error: {e}")

    print(f"  📊 Total Instagram posts: {len(posts)}")
    return posts


# ─── LinkedIn Scraper ────────────────────────────────────────────────────────
def scrape_linkedin(client, config):
    print("\n💼 Scraping LinkedIn...")
    posts = []
    scraping_config = config["scraping"]

    for keyword in scraping_config["keywords"][:8]:
        try:
            actor = config["apify"]["actors"]["linkedin"]
            run_input = {
                "searchTerms": [keyword],
                "maxResults": 15,
                "sortBy": "relevance",
            }
            run = client.actor(actor).call(run_input=run_input)
            dataset = client.dataset(run["defaultDatasetId"])

            for item in dataset.iterate_items():
                post = {
                    "platform": "linkedin",
                    "author": item.get("authorName", item.get("author", "")),
                    "author_name": item.get("authorName", ""),
                    "author_url": item.get("authorProfileUrl", item.get("authorUrl", "")),
                    "author_followers": item.get("authorFollowers", 0),
                    "author_headline": item.get("authorHeadline", ""),
                    "text": item.get("text", item.get("content", "")),
                    "url": item.get("postUrl", item.get("url", "")),
                    "image_url": item.get("imageUrl", item.get("images", [""])[0] if item.get("images") else ""),
                    "video_url": item.get("videoUrl", ""),
                    "likes": item.get("numLikes", item.get("likes", 0)),
                    "comments": item.get("numComments", item.get("comments", 0)),
                    "shares": item.get("numShares", item.get("shares", 0)),
                    "timestamp": item.get("postedAt", item.get("date", "")),
                    "type": "post",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                post["id"] = generate_post_id(post)
                posts.append(post)
                print(f"  ✓ {post['author'][:30]} - {post['likes']} likes")

        except Exception as e:
            print(f"  ✗ LinkedIn search '{keyword}' error: {e}")

    print(f"  📊 Total LinkedIn posts: {len(posts)}")
    return posts


# ─── TikTok Scraper ──────────────────────────────────────────────────────────
def scrape_tiktok(client, config):
    print("\n🎵 Scraping TikTok...")
    posts = []
    scraping_config = config["scraping"]

    for keyword in scraping_config["keywords"][:8]:
        try:
            actor = config["apify"]["actors"]["tiktok"]
            run_input = {
                "searchQueries": [keyword],
                "resultsPerPage": 15,
                "shouldDownloadVideos": False,
            }
            run = client.actor(actor).call(run_input=run_input)
            dataset = client.dataset(run["defaultDatasetId"])

            for item in dataset.iterate_items():
                post = {
                    "platform": "tiktok",
                    "author": item.get("authorMeta", {}).get("name", item.get("author", "")),
                    "author_name": item.get("authorMeta", {}).get("nickName", ""),
                    "author_url": f"https://tiktok.com/@{item.get('authorMeta', {}).get('name', '')}",
                    "author_followers": item.get("authorMeta", {}).get("fans", 0),
                    "text": item.get("text", item.get("desc", "")),
                    "url": item.get("webVideoUrl", item.get("url", "")),
                    "image_url": item.get("videoMeta", {}).get("coverUrl", item.get("covers", [""])[0] if item.get("covers") else ""),
                    "video_url": item.get("videoUrl", ""),
                    "likes": item.get("diggCount", item.get("likes", 0)),
                    "comments": item.get("commentCount", item.get("comments", 0)),
                    "shares": item.get("shareCount", item.get("shares", 0)),
                    "views": item.get("playCount", item.get("views", 0)),
                    "timestamp": item.get("createTimeISO", ""),
                    "hashtags": [h.get("name", "") for h in item.get("hashtags", [])],
                    "type": "video",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                post["id"] = generate_post_id(post)
                posts.append(post)
                print(f"  ✓ @{post['author']} - {post['likes']} likes, {post.get('views', 0)} views")

        except Exception as e:
            print(f"  ✗ TikTok search '{keyword}' error: {e}")

    # Scrape specific profiles
    for profile in scraping_config["profiles_to_track"].get("tiktok", []):
        try:
            profile_input = {
                "profiles": [f"https://tiktok.com/@{profile}"],
                "resultsPerPage": 10,
                "shouldDownloadVideos": False,
            }
            run = client.actor(actor).call(run_input=profile_input)
            dataset = client.dataset(run["defaultDatasetId"])
            for item in dataset.iterate_items():
                post = {
                    "platform": "tiktok",
                    "author": profile,
                    "author_name": item.get("authorMeta", {}).get("nickName", ""),
                    "author_url": f"https://tiktok.com/@{profile}",
                    "author_followers": item.get("authorMeta", {}).get("fans", 0),
                    "text": item.get("text", item.get("desc", "")),
                    "url": item.get("webVideoUrl", ""),
                    "image_url": item.get("videoMeta", {}).get("coverUrl", ""),
                    "video_url": item.get("videoUrl", ""),
                    "likes": item.get("diggCount", 0),
                    "comments": item.get("commentCount", 0),
                    "shares": item.get("shareCount", 0),
                    "views": item.get("playCount", 0),
                    "timestamp": item.get("createTimeISO", ""),
                    "hashtags": [h.get("name", "") for h in item.get("hashtags", [])],
                    "type": "video",
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                post["id"] = generate_post_id(post)
                posts.append(post)
        except Exception as e:
            print(f"  ✗ TikTok profile {profile} error: {e}")

    print(f"  📊 Total TikTok posts: {len(posts)}")
    return posts


# ─── Telegram Bot ────────────────────────────────────────────────────────────
def send_telegram_notification(post, config, category_name):
    tg = config["telegram"]
    if tg["bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
        return

    platform_emoji = {"instagram": "📸", "linkedin": "💼", "tiktok": "🎵"}.get(post["platform"], "📌")
    text_preview = (post.get("text", "") or "")[:300]
    if len(post.get("text", "") or "") > 300:
        text_preview += "..."

    message = f"""{platform_emoji} *פוסט חדש - {category_name}*

👤 *{post.get('author_name') or post.get('author', 'Unknown')}*
📊 Platform: {post['platform'].title()}
❤️ Likes: {post.get('likes', 0):,}
💬 Comments: {post.get('comments', 0):,}

📝 *תוכן:*
{text_preview}

🔗 [צפה בפוסט המקורי]({post.get('url', '#')})
"""

    try:
        url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
        payload = {
            "chat_id": tg["chat_id"],
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        resp = requests.post(url, json=payload, timeout=10)

        # Also send image if available
        if post.get("image_url"):
            photo_url = f"https://api.telegram.org/bot{tg['bot_token']}/sendPhoto"
            photo_payload = {
                "chat_id": tg["chat_id"],
                "photo": post["image_url"],
                "caption": f"{platform_emoji} {post.get('author', '')} - {category_name}",
            }
            requests.post(photo_url, json=photo_payload, timeout=10)

    except Exception as e:
        print(f"  ⚠ Telegram send failed: {e}")


def send_telegram_summary(new_count, db, config):
    tg = config["telegram"]
    if tg["bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
        return

    stats = db["stats"]
    message = f"""📊 *סיכום סריקה - AI Content Scraper*

🆕 פוסטים חדשים: *{new_count}*
📦 סה"כ במאגר: *{stats['total']}*

📱 *לפי פלטפורמה:*
📸 Instagram: {stats['by_platform'].get('instagram', 0)}
💼 LinkedIn: {stats['by_platform'].get('linkedin', 0)}
🎵 TikTok: {stats['by_platform'].get('tiktok', 0)}

🏷️ *לפי קטגוריה:*
"""
    for cat in config["categories"]:
        count = stats["by_category"].get(cat["id"], 0)
        message += f"  • {cat['name_he']}: {count}\n"

    message += f"\n⏰ עדכון אחרון: {datetime.now().strftime('%d/%m/%Y %H:%M')}"

    try:
        url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
        requests.post(url, json={
            "chat_id": tg["chat_id"],
            "text": message,
            "parse_mode": "Markdown",
        }, timeout=10)
    except Exception as e:
        print(f"  ⚠ Telegram summary failed: {e}")


# ─── Main Pipeline ───────────────────────────────────────────────────────────
def run_scraper():
    print("=" * 60)
    print("🤖 AI Content Scraper - Starting...")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    config = load_config()

    # Override config with environment variables (Railway)
    if os.environ.get("APIFY_TOKEN"):
        config["apify"]["token"] = os.environ["APIFY_TOKEN"]
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        config["telegram"]["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
    if os.environ.get("TELEGRAM_CHAT_ID"):
        config["telegram"]["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]

    db = load_db()
    existing_ids = {p["id"] for p in db["posts"]}

    # Initialize Apify client
    client = ApifyClient(config["apify"]["token"])

    # Scrape all platforms
    all_posts = []
    all_posts.extend(scrape_instagram(client, config))
    all_posts.extend(scrape_linkedin(client, config))
    all_posts.extend(scrape_tiktok(client, config))

    # Process & deduplicate
    new_count = 0
    for post in all_posts:
        if post["id"] in existing_ids:
            continue

        # Classify
        post["category"] = classify_post(post.get("text", ""), config)
        category_name = next(
            (c["name_he"] for c in config["categories"] if c["id"] == post["category"]),
            "כללי"
        )

        # Download image
        post["local_image"] = download_image(post.get("image_url"), post["id"])

        # Hebrew rewrite placeholder
        post["hebrew_text"] = None
        post["hebrew_status"] = "pending"

        # Add to DB
        db["posts"].append(post)
        existing_ids.add(post["id"])
        new_count += 1

        # Send Telegram notification
        send_telegram_notification(post, config, category_name)

    # Update stats
    db["stats"]["total"] = len(db["posts"])
    db["stats"]["by_platform"] = {}
    db["stats"]["by_category"] = {}
    for p in db["posts"]:
        platform = p.get("platform", "unknown")
        category = p.get("category", "unknown")
        db["stats"]["by_platform"][platform] = db["stats"]["by_platform"].get(platform, 0) + 1
        db["stats"]["by_category"][category] = db["stats"]["by_category"].get(category, 0) + 1

    db["last_run"] = datetime.now(timezone.utc).isoformat()
    save_db(db)

    # Send summary
    send_telegram_summary(new_count, db, config)

    print(f"\n{'=' * 60}")
    print(f"✅ Done! {new_count} new posts added ({db['stats']['total']} total)")
    print(f"{'=' * 60}")
    return new_count


if __name__ == "__main__":
    run_scraper()

"""
AI Content Scraper - Apify Integration
Scrapes Instagram, LinkedIn & TikTok for AI/GenAI design content.
Categorizes posts, saves to JSON DB, and sends Telegram notifications.
Only keeps carousels from Instagram & LinkedIn. Accepts all TikTok.
"""

import json
import os
import re
import hashlib
from datetime import datetime, timezone, timedelta
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


def is_recent(timestamp_str, max_days=2):
    """Check if a post timestamp is within the last N days."""
    if not timestamp_str:
        return True  # If no timestamp, accept it
    try:
        # Try various timestamp formats
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f+00:00",
                    "%Y-%m-%dT%H:%M:%S+00:00", "%Y-%m-%dT%H:%M:%S"]:
            try:
                ts = datetime.strptime(timestamp_str[:26], fmt[:len(timestamp_str[:26])])
                cutoff = datetime.now() - timedelta(days=max_days)
                return ts > cutoff
            except ValueError:
                continue
        # If we can't parse, try ISO format
        if "T" in str(timestamp_str):
            ts_str = str(timestamp_str).replace("Z", "").split("+")[0][:19]
            ts = datetime.fromisoformat(ts_str)
            cutoff = datetime.now() - timedelta(days=max_days)
            return ts > cutoff
    except Exception:
        pass
    return True  # Accept if we can't parse


def detect_carousel(item):
    """Detect if an item is a carousel/sidecar post. Check multiple field names."""
    # Check type field (various naming conventions)
    post_type = ""
    for key in ["type", "productType", "mediaType", "__typename"]:
        val = (item.get(key) or "")
        if val:
            post_type = str(val).lower()
            break

    if post_type in ("sidecar", "graphsidecar", "carousel", "xdtsidecar", "document"):
        return True

    # Check for multiple child images
    for key in ["childPosts", "sidecarImages", "images", "carouselMedia", "sidecar_edges"]:
        children = item.get(key)
        if isinstance(children, list) and len(children) > 1:
            return True

    # Check childPostsCount
    if (item.get("childPostsCount") or 0) > 1:
        return True

    return False


def extract_carousel_images(item):
    """Extract all image URLs from carousel children."""
    images = []
    for key in ["childPosts", "sidecarImages", "images", "carouselMedia", "sidecar_edges"]:
        children = item.get(key)
        if isinstance(children, list) and len(children) > 0:
            for child in children:
                if isinstance(child, dict):
                    for img_key in ["displayUrl", "url", "src", "imageUrl"]:
                        img = child.get(img_key)
                        if img and isinstance(img, str) and img.startswith("http"):
                            images.append(img)
                            break
                elif isinstance(child, str) and child.startswith("http"):
                    images.append(child)
            if images:
                return images
    return images


# ─── Category Classification ────────────────────────────────────────────────
def classify_post(text, config):
    text_lower = (text or "").lower()
    scores = {}
    for cat in config["categories"]:
        score = sum(1 for kw in cat["keywords"] if kw.lower() in text_lower)
        if score > 0:
            scores[cat["id"]] = score
    if not scores:
        return "trends"
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
    actor = config["apify"]["actors"]["instagram"]

    # Scrape by hashtags
    run_input = {
        "directUrls": [f"https://www.instagram.com/explore/tags/{tag.strip('#')}/"
                       for tag in scraping_config["hashtags_instagram"][:5]],
        "resultsLimit": scraping_config["max_posts_per_run"],
        "resultsType": "posts",
        "searchType": "hashtag",
    }

    try:
        run = client.actor(actor).call(run_input=run_input)
        dataset = client.dataset(run["defaultDatasetId"])
        carousel_count = 0
        other_count = 0

        for item in dataset.iterate_items():
            is_car = detect_carousel(item)
            car_images = extract_carousel_images(item) if is_car else []
            raw_type = item.get("type") or item.get("productType") or item.get("__typename") or "unknown"

            print(f"  📋 type={raw_type} is_carousel={is_car} keys={sorted(item.keys())[:8]}")

            if is_car:
                carousel_count += 1
            else:
                other_count += 1

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
                "type": "carousel" if is_car else str(raw_type).lower(),
                "is_carousel": is_car,
                "carousel_images": car_images,
                "slides_count": len(car_images) if car_images else item.get("childPostsCount", 0),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            post["id"] = generate_post_id(post)
            posts.append(post)
            print(f"  ✓ @{post['author']} - {post['likes']} likes ({post['type']})")

        print(f"  📊 Hashtags: {carousel_count} carousels, {other_count} other")

    except Exception as e:
        print(f"  ✗ Instagram hashtag error: {e}")

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
                is_car = detect_carousel(item)
                car_images = extract_carousel_images(item) if is_car else []
                raw_type = item.get("type") or "unknown"

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
                    "type": "carousel" if is_car else str(raw_type).lower(),
                    "is_carousel": is_car,
                    "carousel_images": car_images,
                    "slides_count": len(car_images) if car_images else 0,
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
                post_type = (item.get("type") or "").lower()
                images = item.get("images") or []
                has_document = item.get("document") or item.get("documentUrl")
                is_car = post_type in ("document", "carousel") or len(images) > 1 or bool(has_document)

                print(f"  📋 LI type={item.get('type')} images={len(images)} doc={bool(has_document)} is_carousel={is_car}")

                post = {
                    "platform": "linkedin",
                    "author": item.get("authorName", item.get("author", "")),
                    "author_name": item.get("authorName", ""),
                    "author_url": item.get("authorProfileUrl", item.get("authorUrl", "")),
                    "author_followers": item.get("authorFollowers", 0),
                    "author_headline": item.get("authorHeadline", ""),
                    "text": item.get("text", item.get("content", "")),
                    "url": item.get("postUrl", item.get("url", "")),
                    "image_url": item.get("imageUrl", images[0] if images else ""),
                    "video_url": item.get("videoUrl", ""),
                    "likes": item.get("numLikes", item.get("likes", 0)),
                    "comments": item.get("numComments", item.get("comments", 0)),
                    "shares": item.get("numShares", item.get("shares", 0)),
                    "timestamp": item.get("postedAt", item.get("date", "")),
                    "type": "carousel" if is_car else "post",
                    "is_carousel": is_car,
                    "carousel_images": images if is_car else [],
                    "slides_count": len(images) if is_car else 0,
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                }
                post["id"] = generate_post_id(post)
                posts.append(post)
                print(f"  ✓ {post['author'][:30]} - {post['likes']} likes ({post['type']})")

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
                    "is_carousel": False,
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
                    "is_carousel": False,
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
    carousel_tag = " 🎠" if post.get("is_carousel") else ""
    text_preview = (post.get("text", "") or "")[:300]
    if len(post.get("text", "") or "") > 300:
        text_preview += "..."

    message = f"""{platform_emoji}{carousel_tag} *פוסט חדש - {category_name}*

👤 *{post.get('author_name') or post.get('author', 'Unknown')}*
📊 {post['platform'].title()} | ❤️ {post.get('likes', 0):,} | 💬 {post.get('comments', 0):,}

📝 {text_preview}

🔗 [צפה בפוסט]({post.get('url', '#')})
"""

    try:
        url = f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": tg["chat_id"],
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }, timeout=10)

        if post.get("image_url"):
            requests.post(f"https://api.telegram.org/bot{tg['bot_token']}/sendPhoto", json={
                "chat_id": tg["chat_id"],
                "photo": post["image_url"],
                "caption": f"{platform_emoji} {post.get('author', '')} - {category_name}",
            }, timeout=10)

    except Exception as e:
        print(f"  ⚠ Telegram send failed: {e}")


def send_telegram_summary(new_count, db, config):
    tg = config["telegram"]
    if tg["bot_token"] == "YOUR_TELEGRAM_BOT_TOKEN":
        return

    stats = db["stats"]
    carousel_count = sum(1 for p in db["posts"] if p.get("is_carousel"))

    message = f"""📊 *סיכום סריקה - AI Content Scraper*

🆕 פוסטים חדשים: *{new_count}*
📦 סה"כ במאגר: *{stats['total']}*
🎠 קרוסלות: *{carousel_count}*

📱 *לפי פלטפורמה:*
📸 Instagram: {stats['by_platform'].get('instagram', 0)}
💼 LinkedIn: {stats['by_platform'].get('linkedin', 0)}
🎵 TikTok: {stats['by_platform'].get('tiktok', 0)}

⏰ עדכון: {datetime.now().strftime('%d/%m/%Y %H:%M')}"""

    try:
        requests.post(f"https://api.telegram.org/bot{tg['bot_token']}/sendMessage", json={
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

    print(f"\n📦 Raw total: {len(all_posts)} posts scraped")

    # ─── Filter & Sort ────────────────────────────────────────────────────
    min_likes = int(os.environ.get("MIN_LIKES", 10))
    max_posts = int(os.environ.get("MAX_POSTS", 300))
    max_telegram = int(os.environ.get("MAX_TELEGRAM", 10))
    min_likes_telegram = int(os.environ.get("MIN_LIKES_TELEGRAM", 50))
    max_days = int(os.environ.get("MAX_DAYS", 2))

    candidates = []
    skipped_dup = 0
    skipped_old = 0
    skipped_low = 0

    for post in all_posts:
        if post["id"] in existing_ids:
            skipped_dup += 1
            continue

        # Filter: only last N days
        if not is_recent(post.get("timestamp"), max_days):
            skipped_old += 1
            continue

        # Filter: minimum engagement
        post_likes = post.get("likes", 0) or 0
        if post_likes < min_likes:
            skipped_low += 1
            continue

        candidates.append(post)

    # Sort: carousels first, then by likes
    candidates.sort(key=lambda p: (
        1 if p.get("is_carousel") else 0,  # carousels first
        p.get("likes", 0) or 0              # then by likes
    ), reverse=True)

    top_posts = candidates[:max_posts]

    print(f"  📊 {len(candidates)} passed filters, keeping top {len(top_posts)}")
    print(f"  📊 Skipped: {skipped_dup} duplicates, {skipped_old} old (>{max_days}d), {skipped_low} low (<{min_likes} likes)")
    carousels_in = sum(1 for p in top_posts if p.get("is_carousel"))
    print(f"  🎠 Carousels in final set: {carousels_in}/{len(top_posts)}")

    new_count = 0
    telegram_sent = 0
    for post in top_posts:
        post["category"] = classify_post(post.get("text", ""), config)
        category_name = next(
            (c["name_he"] for c in config["categories"] if c["id"] == post["category"]),
            "כללי"
        )
        post["local_image"] = download_image(post.get("image_url"), post["id"])
        post["hebrew_text"] = None
        post["hebrew_status"] = "pending"

        db["posts"].append(post)
        existing_ids.add(post["id"])
        new_count += 1

        # Telegram: send carousels first, then top liked
        post_likes = post.get("likes", 0) or 0
        if telegram_sent < max_telegram and (post.get("is_carousel") or post_likes >= min_likes_telegram):
            send_telegram_notification(post, config, category_name)
            telegram_sent += 1

    print(f"  ✅ Added {new_count} posts, sent {telegram_sent} Telegram notifications")

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

    send_telegram_summary(new_count, db, config)

    print(f"\n{'=' * 60}")
    print(f"✅ Done! {new_count} new posts added ({db['stats']['total']} total)")
    print(f"{'=' * 60}")
    return new_count


if __name__ == "__main__":
    run_scraper()

"""
Image Generator - Hebrew Carousel Graphics
Takes scraped posts with Hebrew text and generates carousel images
using Google Gemini API image generation.
"""

import json
import os
import sys
import base64
import re
from pathlib import Path
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    os.system("pip install requests --break-system-packages -q")
    import requests

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "data" / "posts.json"
GENERATED_DIR = BASE_DIR / "data" / "generated"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_db():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ─── Slide Text Splitter ──────────────────────────────────────────────────
def split_to_slides(hebrew_text, num_slides):
    """Split Hebrew text into slide-sized chunks matching the original slide count."""
    if not hebrew_text:
        return []

    # Clean up the text
    text = hebrew_text.strip()

    # Try to split by double newlines first (natural paragraph breaks)
    paragraphs = [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]

    if len(paragraphs) >= num_slides:
        # Distribute paragraphs across slides
        slides = []
        per_slide = max(1, len(paragraphs) // num_slides)
        for i in range(num_slides):
            start = i * per_slide
            end = start + per_slide if i < num_slides - 1 else len(paragraphs)
            slide_text = '\n\n'.join(paragraphs[start:end])
            slides.append(slide_text)
        return slides

    # If not enough paragraphs, split by sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) >= num_slides:
        slides = []
        per_slide = max(1, len(sentences) // num_slides)
        for i in range(num_slides):
            start = i * per_slide
            end = start + per_slide if i < num_slides - 1 else len(sentences)
            slide_text = ' '.join(sentences[start:end])
            slides.append(slide_text)
        return slides

    # Fallback: just repeat the text across slides with different framing
    slides = []
    words = text.split()
    per_slide = max(1, len(words) // num_slides)
    for i in range(num_slides):
        start = i * per_slide
        end = start + per_slide if i < num_slides - 1 else len(words)
        slides.append(' '.join(words[start:end]))
    return slides


# ─── Gemini Image Generation ──────────────────────────────────────────────
def generate_slide_image(gemini_key, slide_text, slide_num, total_slides, category, platform):
    """Generate a single carousel slide image using Gemini."""

    slide_context = ""
    if slide_num == 1:
        slide_context = "זו שקופית הפתיחה/כותרת של הקרוסלה. צריכה לתפוס תשומת לב ולהיות מושכת."
    elif slide_num == total_slides:
        slide_context = "זו שקופית הסיום. צריכה לכלול קריאה לפעולה או סיכום."
    else:
        slide_context = f"זו שקופית {slide_num} מתוך {total_slides}. שקופית תוכן."

    prompt = f"""Create a professional, modern social media carousel slide image.

Requirements:
- The slide MUST contain the following Hebrew text (RTL direction): "{slide_text}"
- Modern, clean design with gradient background
- Professional typography for Hebrew text
- {slide_context}
- Slide {slide_num} of {total_slides}
- Category: {category}
- Platform style: {platform}
- Use modern colors (dark backgrounds with accent colors like purple, blue, or gradient)
- The Hebrew text should be large, readable, and be the main focus
- Add subtle design elements (lines, shapes, icons) but keep text as hero
- Aspect ratio: square (1:1) for Instagram, or 4:5 portrait
- Do NOT add any English text
- Make it look like a professional Israeli content creator made it"""

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                    "responseMimeType": "image/png",
                }
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract image from response
        candidates = data.get("candidates", [])
        if not candidates:
            print(f"    ⚠ No candidates in Gemini response")
            return None

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                image_data = part["inlineData"].get("data", "")
                mime_type = part["inlineData"].get("mimeType", "image/png")
                if image_data:
                    return base64.b64decode(image_data)

        print(f"    ⚠ No image data in Gemini response")
        return None

    except Exception as e:
        print(f"    ⚠ Gemini image generation error: {e}")
        return None


def generate_carousel(post, config):
    """Generate full carousel images for a post."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        print("  ⚠ GEMINI_API_KEY not set, skipping image generation")
        return None

    hebrew_text = post.get("hebrew_text", "")
    if not hebrew_text:
        return None

    # Determine number of slides from original post
    original_images = post.get("carousel_images", [])
    original_slides_count = post.get("slides_count", 0)

    # Detect slide count from original data
    if original_slides_count > 0:
        num_slides = original_slides_count
    elif len(original_images) > 0:
        num_slides = len(original_images)
    else:
        # Default: estimate from text length
        text_len = len(hebrew_text)
        if text_len < 200:
            num_slides = 3
        elif text_len < 500:
            num_slides = 5
        else:
            num_slides = 7

    # Cap at reasonable number
    num_slides = min(num_slides, 10)

    category_name = next(
        (c["name_he"] for c in config["categories"] if c["id"] == post.get("category")),
        "כללי"
    )

    # Split text into slides
    slide_texts = split_to_slides(hebrew_text, num_slides)

    print(f"  🎨 Generating {num_slides} slide images...")

    # Create output directory for this post
    post_dir = GENERATED_DIR / post["id"]
    post_dir.mkdir(parents=True, exist_ok=True)

    generated_paths = []
    for i, slide_text in enumerate(slide_texts, 1):
        print(f"    📸 Slide {i}/{num_slides}...")

        image_data = generate_slide_image(
            gemini_key,
            slide_text,
            slide_num=i,
            total_slides=num_slides,
            category=category_name,
            platform=post.get("platform", "instagram"),
        )

        if image_data:
            filepath = post_dir / f"slide_{i:02d}.png"
            with open(filepath, "wb") as f:
                f.write(image_data)
            generated_paths.append(str(filepath))
            print(f"    ✅ Slide {i} saved ({len(image_data) // 1024}KB)")
        else:
            print(f"    ❌ Slide {i} failed")

    return generated_paths if generated_paths else None


# ─── Send to Telegram ─────────────────────────────────────────────────────
def send_carousel_to_telegram(post, image_paths, config):
    """Send generated carousel images to Telegram as a media group (album)."""
    tg = config.get("telegram", {})
    token = os.environ.get("TELEGRAM_BOT_TOKEN", tg.get("bot_token", ""))
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", tg.get("chat_id", ""))

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN" or not chat_id:
        return

    category_name = next(
        (c["name_he"] for c in config["categories"] if c["id"] == post.get("category")),
        "כללי"
    )

    platform_emoji = {"instagram": "📸", "linkedin": "💼", "tiktok": "🎵"}.get(post["platform"], "📌")

    caption = f"""{platform_emoji} *קרוסלה בעברית - {category_name}*

👤 *{post.get('author_name') or post.get('author', 'Unknown')}*
❤️ {post.get('likes', 0):,} לייקים

📝 {(post.get('hebrew_text', '') or '')[:300]}

🔗 [פוסט מקורי]({post.get('url', '#')})"""

    try:
        if len(image_paths) == 1:
            # Single image
            with open(image_paths[0], "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={
                        "chat_id": chat_id,
                        "caption": caption[:1024],
                        "parse_mode": "Markdown",
                    },
                    files={"photo": f},
                    timeout=30,
                )
            return resp.json()
        else:
            # Multiple images - send as media group (album)
            media = []
            files = {}
            for i, path in enumerate(image_paths[:10]):  # Telegram max 10 per album
                file_key = f"photo_{i}"
                files[file_key] = open(path, "rb")
                media_item = {
                    "type": "photo",
                    "media": f"attach://{file_key}",
                }
                if i == 0:
                    media_item["caption"] = caption[:1024]
                    media_item["parse_mode"] = "Markdown"
                media.append(media_item)

            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMediaGroup",
                data={
                    "chat_id": chat_id,
                    "media": json.dumps(media),
                },
                files=files,
                timeout=60,
            )

            # Close file handles
            for f in files.values():
                f.close()

            return resp.json()

    except Exception as e:
        print(f"  ⚠ Telegram carousel send failed: {e}")
        return None


# ─── Main Pipeline ────────────────────────────────────────────────────────
def generate_pending_images(limit=5):
    """Generate carousel images for posts that have Hebrew text but no generated images."""
    print("=" * 60)
    print("🎨 Image Generator - Starting...")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    db = load_db()
    config = load_config()

    # Find posts with Hebrew text but no generated images
    pending = [
        p for p in db["posts"]
        if p.get("hebrew_status") == "done"
        and p.get("hebrew_text")
        and not p.get("generated_images")
    ]

    if not pending:
        print("✅ No posts pending image generation!")
        return 0

    # Sort by likes (prioritize popular content)
    pending.sort(key=lambda p: p.get("likes", 0), reverse=True)
    to_process = pending[:limit]

    print(f"🖼️ Processing {len(to_process)} posts (out of {len(pending)} pending)...\n")

    success_count = 0
    for i, post in enumerate(to_process, 1):
        print(f"\n  [{i}/{len(to_process)}] @{post.get('author', 'unknown')} ({post['platform']}) - {post.get('likes', 0)} likes")

        image_paths = generate_carousel(post, config)

        if image_paths:
            # Update in the DB
            for db_post in db["posts"]:
                if db_post["id"] == post["id"]:
                    db_post["generated_images"] = image_paths
                    db_post["images_generated_at"] = datetime.now(timezone.utc).isoformat()
                    db_post["images_count"] = len(image_paths)
                    break

            # Send to Telegram
            print(f"  📤 Sending carousel to Telegram...")
            result = send_carousel_to_telegram(post, image_paths, config)
            if result:
                print(f"  ✅ Sent {len(image_paths)} images to Telegram!")

            success_count += 1
        else:
            print(f"  ❌ Image generation failed for this post")

    save_db(db)

    print(f"\n{'=' * 60}")
    print(f"✅ Done! {success_count}/{len(to_process)} carousels generated")
    print(f"{'=' * 60}")
    return success_count


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    generate_pending_images(limit)

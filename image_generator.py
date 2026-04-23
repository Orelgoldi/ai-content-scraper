"""
Image Generator - Hebrew Carousel Graphics
Takes scraped posts with Hebrew text and generates carousel images.
Supports: OpenAI (gpt-image-2) and Google Gemini (Nano Banana 2).
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


# ─── Style Presets ────────────────────────────────────────────────────────
STYLE_PRESETS = {
    "original": "Keep the EXACT same visual design, layout, colors, fonts, and style as the original image. Only replace the text.",
    "modern_dark": "Modern dark design with gradient background (dark purple/blue/black). Neon accent colors. Clean geometric shapes.",
    "minimalist": "Minimalist white/light background. Lots of whitespace. Simple typography. Subtle shadows.",
    "gradient_bold": "Bold colorful gradients (pink, purple, orange). Large bold text. Energetic and eye-catching.",
    "professional": "Professional corporate look. Navy/dark blue tones. Clean lines. Business-appropriate.",
    "creative": "Creative and artistic. Brush strokes, textures, organic shapes. Warm earthy or vibrant colors.",
    "tech": "Tech/futuristic style. Dark background with glowing elements, circuit patterns, matrix-like accents.",
    "pastel": "Soft pastel colors (pink, mint, lavender). Rounded shapes. Friendly and approachable.",
    "custom": "",  # User provides their own style description
}


# ─── Download Image Helper ───────────────────────────────────────────────
def download_image_to_base64(url, timeout=20):
    """Download an image URL and return (base64_data, mime_type) or (None, None)."""
    try:
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ContentScraper/1.0)"
        })
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if "webp" in url or "webp" in content_type:
            content_type = "image/webp"
        elif "png" in url:
            content_type = "image/png"
        elif content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            content_type = "image/jpeg"
        b64 = base64.b64encode(resp.content).decode()
        return b64, content_type
    except Exception as e:
        print(f"    ⚠ Image download failed: {e}")
        return None, None


# ─── OpenAI Image Generation ─────────────────────────────────────────────
def generate_slide_openai(openai_key, slide_text, original_image_url=None, slide_num=1, total_slides=1, style="original"):
    """Generate/edit a slide using OpenAI gpt-image-2."""

    style_desc = STYLE_PRESETS.get(style, STYLE_PRESETS["original"])
    if style == "custom" and not style_desc:
        style_desc = "Keep the same style as the original."

    # ── If we have an original image, use the EDIT endpoint ──────────
    if original_image_url:
        print(f"    📎 Downloading original slide {slide_num} for OpenAI edit...")
        b64, mime = download_image_to_base64(original_image_url)

        if b64:
            import tempfile
            # Save image to temp file for multipart upload
            ext = "png" if "png" in (mime or "") else "jpg"
            tmp_path = tempfile.mktemp(suffix=f".{ext}")
            with open(tmp_path, "wb") as f:
                f.write(base64.b64decode(b64))

            if style == "original":
                edit_prompt = f"""Recreate this exact carousel slide image but replace ALL text with the following Hebrew text (RTL, right-to-left direction):

"{slide_text}"

Keep the EXACT same visual design, layout, colors, background, graphics, and decorative elements. Only change the text from English to Hebrew. The Hebrew text must read right-to-left. Do NOT add any English text."""
            else:
                edit_prompt = f"""Redesign this carousel slide with a new style. Replace all text with Hebrew (RTL):

"{slide_text}"

New style: {style_desc}
Keep the content structure but apply the new design. No English text. Slide {slide_num}/{total_slides}."""

            try:
                with open(tmp_path, "rb") as img_file:
                    resp = requests.post(
                        "https://api.openai.com/v1/images/edits",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        data={
                            "model": "gpt-image-2",
                            "prompt": edit_prompt,
                            "size": "1024x1024",
                            "quality": "high",
                        },
                        files={"image": (f"slide.{ext}", img_file, mime or "image/png")},
                        timeout=120,
                    )
                resp.raise_for_status()
                data = resp.json()

                # Extract image
                if data.get("data") and len(data["data"]) > 0:
                    img_b64 = data["data"][0].get("b64_json", "")
                    if img_b64:
                        return base64.b64decode(img_b64)
                    # If URL returned instead
                    img_url = data["data"][0].get("url", "")
                    if img_url:
                        dl_resp = requests.get(img_url, timeout=30)
                        dl_resp.raise_for_status()
                        return dl_resp.content

                print(f"    ⚠ OpenAI edit: no image in response")
                return None

            except requests.exceptions.HTTPError as e:
                print(f"    ⚠ OpenAI edit HTTP error: {e}")
                try:
                    print(f"    ⚠ Response: {e.response.text[:500]}")
                except:
                    pass
                # Fallback to generations endpoint
                print(f"    🔄 Falling back to OpenAI generations...")
            except Exception as e:
                print(f"    ⚠ OpenAI edit error: {e}")
                print(f"    🔄 Falling back to OpenAI generations...")
            finally:
                try:
                    os.unlink(tmp_path)
                except:
                    pass

    # ── Fallback or no original: use GENERATIONS endpoint ────────────
    gen_prompt = f"""Create a professional social media carousel slide for Instagram.

The slide MUST contain this Hebrew text (RTL, right-to-left direction):
"{slide_text}"

Style: {style_desc}
Slide {slide_num} of {total_slides}.
Do NOT include any English text. The Hebrew text should be large, readable, and the main focus.
Make it look like a professional Israeli content creator made it."""

    try:
        resp = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-image-2",
                "prompt": gen_prompt,
                "size": "1024x1024",
                "quality": "high",
                "n": 1,
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("data") and len(data["data"]) > 0:
            img_b64 = data["data"][0].get("b64_json", "")
            if img_b64:
                return base64.b64decode(img_b64)
            img_url = data["data"][0].get("url", "")
            if img_url:
                dl_resp = requests.get(img_url, timeout=30)
                dl_resp.raise_for_status()
                return dl_resp.content

        print(f"    ⚠ OpenAI generations: no image in response")
        return None

    except requests.exceptions.HTTPError as e:
        print(f"    ⚠ OpenAI generations HTTP error: {e}")
        try:
            print(f"    ⚠ Response: {e.response.text[:500]}")
        except:
            pass
        return None
    except Exception as e:
        print(f"    ⚠ OpenAI generations error: {e}")
        return None


# ─── Gemini Image Generation ──────────────────────────────────────────────
def generate_slide_image(gemini_key, slide_text, original_image_url=None, slide_num=1, total_slides=1, style="original", extra_reference_url=None):
    """
    Generate a carousel slide by taking the ORIGINAL image and recreating it with Hebrew text.
    If no original image, generates from scratch.
    """

    # ── Build the prompt ──────────────────────────────────────────────
    style_desc = STYLE_PRESETS.get(style, STYLE_PRESETS["original"])
    if style == "custom" and not style_desc:
        style_desc = "Keep the same style as the original."

    parts = []

    # ── Attach original image (the core of the approach) ─────────────
    if original_image_url:
        print(f"    📎 Downloading original slide {slide_num}...")
        b64, mime = download_image_to_base64(original_image_url)
        if b64:
            parts.append({
                "inline_data": {"mime_type": mime, "data": b64}
            })
            print(f"    ✅ Original image loaded")

            if style == "original":
                # EXACT recreation with Hebrew text
                parts.append({"text": f"""Look at this carousel slide image carefully.

YOUR TASK: Recreate this EXACT image but replace ALL text with the following Hebrew text (RTL, right-to-left direction):

"{slide_text}"

CRITICAL RULES:
1. Keep the EXACT SAME visual design — same layout, same colors, same background, same graphics, same icons, same decorative elements
2. ONLY change the text content from English to the Hebrew text above
3. Hebrew text must read right-to-left (RTL direction)
4. Keep the same font sizes, text positions, and text hierarchy
5. Keep the same aspect ratio as the original
6. Do NOT add any English text
7. The result should look like the original creator made a Hebrew version of their own post"""})
            else:
                # Redesign with a new style but same content
                parts.append({"text": f"""Look at this carousel slide image. I want you to recreate it with a NEW style but with Hebrew text.

HEBREW TEXT (RTL, right-to-left):
"{slide_text}"

NEW DESIGN STYLE:
{style_desc}

RULES:
1. Use the original image as reference for content structure and text hierarchy
2. Apply the new design style described above
3. Replace ALL text with the Hebrew text provided
4. Hebrew must read right-to-left (RTL)
5. Keep the same aspect ratio
6. Do NOT include any English text
7. Slide {slide_num} of {total_slides}"""})
        else:
            # Fallback: couldn't download original, generate from scratch
            print(f"    ⚠ Could not download original, generating from scratch")
            parts.append({"text": f"""Create a social media carousel slide image.

The slide must contain this Hebrew text (RTL, right-to-left): "{slide_text}"

Style: {style_desc}
Slide {slide_num} of {total_slides}. No English text. Square aspect ratio."""})
    else:
        # No original image available
        parts.append({"text": f"""Create a social media carousel slide image.

The slide must contain this Hebrew text (RTL, right-to-left): "{slide_text}"

Style: {style_desc}
Slide {slide_num} of {total_slides}. No English text. Square aspect ratio."""})

    # ── Attach extra reference image if provided ─────────────────────
    if extra_reference_url:
        ref_b64, ref_mime = download_image_to_base64(extra_reference_url)
        if ref_b64:
            parts.insert(0, {"inline_data": {"mime_type": ref_mime, "data": ref_b64}})
            # Update prompt to mention the style reference
            for i, p in enumerate(parts):
                if "text" in p:
                    parts[i]["text"] = "I've attached a STYLE REFERENCE image first. Match its visual style. " + p["text"]
                    break
            print(f"    ✅ Style reference image attached")

    # ── Call Gemini API ───────────────────────────────────────────────
    try:
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-image-preview:generateContent",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": gemini_key,
            },
            json={
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                }
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract image from response
        candidates = data.get("candidates", [])
        if not candidates:
            print(f"    ⚠ No candidates in Gemini response")
            print(f"    ⚠ Response: {json.dumps(data)[:500]}")
            return None

        parts_resp = candidates[0].get("content", {}).get("parts", [])
        for part in parts_resp:
            if "inlineData" in part:
                image_data = part["inlineData"].get("data", "")
                if image_data:
                    return base64.b64decode(image_data)

        print(f"    ⚠ No image data in response")
        return None

    except requests.exceptions.HTTPError as e:
        print(f"    ⚠ Gemini API HTTP error: {e}")
        try:
            print(f"    ⚠ Response body: {e.response.text[:500]}")
        except:
            pass
        return None
    except Exception as e:
        print(f"    ⚠ Gemini error: {e}")
        return None


def generate_carousel(post, config, style="original", reference_url=None, engine="auto"):
    """Generate Hebrew carousel by recreating original slides with translated text.
    engine: 'openai', 'gemini', or 'auto' (tries OpenAI first, falls back to Gemini)
    """
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    # Determine which engine to use
    if engine == "auto":
        engine = "openai" if openai_key else "gemini"
    if engine == "openai" and not openai_key:
        print("  ⚠ OPENAI_API_KEY not set, falling back to Gemini")
        engine = "gemini"
    if engine == "gemini" and not gemini_key:
        print("  ⚠ GEMINI_API_KEY not set")
        if openai_key:
            print("  🔄 Falling back to OpenAI")
            engine = "openai"
        else:
            print("  ❌ No API keys configured!")
            return None

    print(f"  🤖 Using engine: {engine.upper()}")

    hebrew_text = post.get("hebrew_text", "")
    if not hebrew_text:
        return None

    # Get original carousel images — these are the images we'll recreate in Hebrew
    original_images = post.get("carousel_images", [])
    num_slides = len(original_images) if original_images else post.get("slides_count", 0)

    if num_slides == 0:
        # Fallback: estimate from text
        text_len = len(hebrew_text)
        num_slides = 3 if text_len < 200 else (5 if text_len < 500 else 7)

    # Cap at reasonable number
    num_slides = min(num_slides, 10)

    # Split Hebrew text to match original slide count
    slide_texts = split_to_slides(hebrew_text, num_slides)

    print(f"  🎨 Recreating {num_slides} slides in Hebrew (style: {style})...")
    if original_images:
        print(f"  📎 Using {len(original_images)} original images as base")
    else:
        print(f"  ⚠ No original images found, generating from scratch")

    # Create output directory
    post_dir = GENERATED_DIR / post["id"]
    post_dir.mkdir(parents=True, exist_ok=True)

    generated_paths = []
    for i, slide_text in enumerate(slide_texts, 1):
        print(f"    📸 Slide {i}/{num_slides}...")

        # Get the matching original image URL (if available)
        original_url = original_images[i - 1] if i - 1 < len(original_images) else None

        if engine == "openai":
            image_data = generate_slide_openai(
                openai_key,
                slide_text,
                original_image_url=original_url,
                slide_num=i,
                total_slides=num_slides,
                style=style,
            )
        else:
            image_data = generate_slide_image(
                gemini_key,
                slide_text,
                original_image_url=original_url,
                slide_num=i,
                total_slides=num_slides,
                style=style,
                extra_reference_url=reference_url if i == 1 else None,
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

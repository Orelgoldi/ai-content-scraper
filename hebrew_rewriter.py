"""
Hebrew Content Rewriter - Nano Banana MCP Integration
Rewrites scraped posts into natural Israeli Hebrew copy.
Uses Nano Banana MCP for AI-powered localization.
"""

import json
import os
import sys
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


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_db():
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ─── Hebrew Rewriting Prompt ────────────────────────────────────────────────
REWRITE_SYSTEM_PROMPT = """אתה קופירייטר ישראלי מנוסה שמתמחה בתוכן דיגיטלי.

המטרה שלך: לקחת פוסט באנגלית על AI, עיצוב UI/UX ובניית אתרים, ולכתוב אותו מחדש בעברית ישראלית טבעית.

כללים חשובים:
1. **אל תתרגם** - כתוב מחדש מאפס. הטקסט צריך להישמע כאילו ישראלי כתב אותו מלכתחילה.
2. **שמור על הקופי ישראלי** - השתמש בסלנג מקצועי מקומי, לא בתרגום מילולי.
3. **שמור על הטון** - אם הפוסט המקורי הומוריסטי, תשמור על הומור. אם מקצועי, תשמור על רצינות.
4. **מונחים טכניים** - השאר מונחים כמו AI, UI, UX, SaaS באנגלית. אל תתרגם שמות כלים.
5. **אורך** - שמור על אורך דומה לפוסט המקורי, אבל אל תתפשר על טבעיות.
6. **הוסף קריאה לפעולה** אם רלוונטי (לא חובה).
7. **אמוג'י** - השתמש באמוג'י בצורה מאופקת ורלוונטית, לא מוגזם.

דוגמאות לקופי ישראלי טוב:
- "הכלי הזה פשוט שבר לי ת'ראש" (במקום "This tool blew my mind")
- "מי שלא משתמש בזה ב-2026 פשוט מפספס" (במקום "If you're not using this in 2026, you're missing out")
- "בניתי לנדינג פייג' מלא ב-12 דקות. בלי קוד. בלי תירוצים." (במקום "Built a full landing page in 12 minutes. No code. No excuses.")

החזר **רק** את הטקסט בעברית, בלי הסברים נוספים."""


def rewrite_with_nano_banana(text, category, platform):
    """
    Rewrite post content to Hebrew using Nano Banana MCP.

    Nano Banana MCP integration options:
    1. Direct API call to Nano Banana endpoint
    2. Via Claude/Anthropic API with Nano Banana tools
    3. Via local MCP server connection

    Configure your preferred method below.
    """

    # ─── Option 1: Nano Banana MCP Direct ────────────────────────────────
    # If Nano Banana provides a direct API endpoint:
    nano_banana_url = os.environ.get("NANO_BANANA_URL", "")
    nano_banana_key = os.environ.get("NANO_BANANA_API_KEY", "")

    if nano_banana_url and nano_banana_key:
        try:
            platform_context = {
                "instagram": "הפוסט מיועד לאינסטגרם - קצר, ויזואלי, עם האשטגים",
                "linkedin": "הפוסט מיועד ללינקדאין - מקצועי אבל נגיש, עם תובנות",
                "tiktok": "הפוסט מיועד לטיקטוק - צעיר, דינמי, תפיסת תשומת לב מהירה",
            }

            payload = {
                "messages": [
                    {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": f"""פלטפורמה: {platform}
קטגוריה: {category}
הקשר: {platform_context.get(platform, '')}

פוסט מקורי:
{text}

כתוב מחדש בעברית ישראלית:"""}
                ],
                "max_tokens": 1000,
                "temperature": 0.7,
            }

            resp = requests.post(
                nano_banana_url,
                headers={
                    "Authorization": f"Bearer {nano_banana_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("content", result.get("text", result.get("choices", [{}])[0].get("message", {}).get("content", "")))

        except Exception as e:
            print(f"  ⚠ Nano Banana API error: {e}")

    # ─── Option 2: Anthropic API Fallback ────────────────────────────────
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if anthropic_key:
        try:
            platform_context = {
                "instagram": "הפוסט מיועד לאינסטגרם - קצר, ויזואלי, עם האשטגים",
                "linkedin": "הפוסט מיועד ללינקדאין - מקצועי אבל נגיש, עם תובנות",
                "tiktok": "הפוסט מיועד לטיקטוק - צעיר, דינמי, תפיסת תשומת לב מהירה",
            }

            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1000,
                    "system": REWRITE_SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": f"""פלטפורמה: {platform}
קטגוריה: {category}
הקשר: {platform_context.get(platform, '')}

פוסט מקורי:
{text}

כתוב מחדש בעברית ישראלית:"""}
                    ],
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"]

        except Exception as e:
            print(f"  ⚠ Anthropic API error: {e}")

    # ─── No API configured ──────────────────────────────────────────────
    print("  ⚠ No AI API configured. Set NANO_BANANA_URL + NANO_BANANA_API_KEY or ANTHROPIC_API_KEY")
    return None


# ─── Main Pipeline ───────────────────────────────────────────────────────
def rewrite_pending_posts(limit=10):
    """Rewrite pending posts to Hebrew."""
    print("=" * 60)
    print("🇮🇱 Hebrew Rewriter - Starting...")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    db = load_db()
    config = load_config()

    pending = [p for p in db["posts"] if p.get("hebrew_status") == "pending"]

    if not pending:
        print("✅ No pending posts to rewrite!")
        return 0

    # Sort by likes (prioritize popular content)
    pending.sort(key=lambda p: p.get("likes", 0), reverse=True)
    to_process = pending[:limit]

    print(f"📝 Processing {len(to_process)} posts (out of {len(pending)} pending)...\n")

    success_count = 0
    for i, post in enumerate(to_process, 1):
        text = post.get("text", "")
        if not text or len(text) < 20:
            print(f"  [{i}] Skipping - text too short")
            continue

        print(f"  [{i}/{len(to_process)}] @{post.get('author', 'unknown')} ({post['platform']}) - {post.get('likes', 0)} likes")

        category_name = next(
            (c["name_he"] for c in config["categories"] if c["id"] == post.get("category")),
            "כללי"
        )

        hebrew_text = rewrite_with_nano_banana(text, category_name, post["platform"])

        if hebrew_text:
            # Update in the DB
            for db_post in db["posts"]:
                if db_post["id"] == post["id"]:
                    db_post["hebrew_text"] = hebrew_text
                    db_post["hebrew_status"] = "done"
                    db_post["hebrew_rewritten_at"] = datetime.now(timezone.utc).isoformat()
                    break
            success_count += 1
            print(f"    ✅ Rewritten successfully")
            print(f"    📝 {hebrew_text[:80]}...")
        else:
            print(f"    ❌ Failed to rewrite")

    save_db(db)

    print(f"\n{'=' * 60}")
    print(f"✅ Done! {success_count}/{len(to_process)} posts rewritten to Hebrew")
    print(f"{'=' * 60}")
    return success_count


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    rewrite_pending_posts(limit)

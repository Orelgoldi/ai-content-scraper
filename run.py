"""
AI Content Scraper - Main Runner
Run the full pipeline: Scrape → Categorize → Rewrite → Notify
Serves dashboard on port 8080 and runs scraping on schedule.
"""

import sys
import os
import time
import threading
import http.server
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
PORT = int(os.environ.get("PORT", 8080))
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", 28800))  # Default: every 8 hours (3 runs/day)


def run_pipeline():
    """Run the full scrape → rewrite → notify pipeline."""
    print(f"\n🚀 Running full pipeline... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n")

    try:
        # Step 0: Clean old non-carousel / non-Instagram posts from DB
        db_path = BASE_DIR / "data" / "posts.json"
        if db_path.exists():
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            before = len(db.get("posts", []))
            db["posts"] = [p for p in db.get("posts", []) if p.get("is_carousel") and p.get("platform") == "instagram"]
            after = len(db["posts"])
            if before != after:
                print(f"🧹 Cleaned DB: removed {before - after} non-carousel/non-Instagram posts (kept {after})")
                with open(db_path, "w", encoding="utf-8") as f:
                    json.dump(db, f, ensure_ascii=False, indent=2)

        # Step 1: Scrape (Instagram carousels only)
        from scraper import run_scraper
        new_posts = run_scraper()

        # Step 2: Rewrite to Hebrew
        if new_posts > 0:
            from hebrew_rewriter import rewrite_pending_posts
            rewrite_pending_posts(limit=new_posts)

        # Step 3: Generate Hebrew carousel images
        # NOTE: Automatic image generation disabled - now triggered manually via dashboard
        # POST /api/generate/{post_id} endpoint handles on-demand generation
        # from image_generator import generate_pending_images
        # generate_pending_images(limit=min(new_posts, 5) if new_posts > 0 else 5)

        # Step 4: Send Telegram digest
        os.system(f"{sys.executable} telegram_bot.py digest")

        print(f"\n✅ Pipeline complete! Next run in {SCRAPE_INTERVAL // 60} minutes.\n")
    except Exception as e:
        print(f"\n❌ Pipeline error: {e}\n")


def scheduled_scraper():
    """Run the pipeline on a schedule in a background thread."""
    # Wait a bit before first run to let the server start
    time.sleep(5)

    while True:
        try:
            run_pipeline()
        except Exception as e:
            print(f"❌ Scheduler error: {e}")

        time.sleep(SCRAPE_INTERVAL)


class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler that serves dashboard and API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def _send_cors_headers(self):
        """Send CORS headers for cross-origin requests."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Handle POST API endpoints."""
        # POST /api/generate/{post_id} - Generate images for a specific post
        if self.path.startswith("/api/generate/"):
            post_id = self.path[len("/api/generate/"):]
            self._handle_generate(post_id)
            return

        self.send_response(404)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

    def _handle_generate(self, post_id):
        """Generate carousel images for a specific post on demand."""
        db_path = BASE_DIR / "data" / "posts.json"

        try:
            # Load the database
            if not db_path.exists():
                self._send_json_error(404, "Database not found")
                return

            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)

            # Find the post by id
            post = None
            post_index = None
            for i, p in enumerate(db.get("posts", [])):
                if p.get("id") == post_id:
                    post = p
                    post_index = i
                    break

            if post is None:
                self._send_json_error(404, f"Post not found: {post_id}")
                return

            # Check prerequisites
            if post.get("hebrew_status") != "done":
                self._send_json_error(400, f"Post hebrew_status is '{post.get('hebrew_status')}', expected 'done'")
                return

            if not post.get("hebrew_text"):
                self._send_json_error(400, "Post has no hebrew_text")
                return

            # Load config
            config_path = BASE_DIR / "config.json"
            config = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            # Read POST body for style and reference options
            content_length = int(self.headers.get('Content-Length', 0))
            body = {}
            if content_length > 0:
                raw = self.rfile.read(content_length)
                try:
                    body = json.loads(raw.decode('utf-8'))
                except:
                    pass

            style = body.get("style", "modern_dark")
            reference_url = body.get("reference_url", None)
            custom_style = body.get("custom_style", "")

            # If custom style text provided, use it
            if style == "custom" and custom_style:
                from image_generator import STYLE_PRESETS
                STYLE_PRESETS["custom"] = custom_style

            # Generate carousel images
            from image_generator import generate_carousel
            result = generate_carousel(post, config, style=style, reference_url=reference_url)

            if result is None:
                self._send_json_error(500, "Image generation returned no results - check Gemini API key and model")
                return

            # Update the post in the database
            db["posts"][post_index]["generated_images"] = result
            db["posts"][post_index]["images_generated_at"] = datetime.now().isoformat()
            db["posts"][post_index]["images_count"] = len(result)

            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)

            # Send success response
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "post_id": post_id,
                "images_count": len(result),
                "generated_images": result
            }, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self._send_json_error(500, f"Generation failed: {str(e)}")

    def _send_json_error(self, status_code, message):
        """Send a JSON error response with CORS headers."""
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({
            "success": False,
            "error": message
        }, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        # Redirect root to dashboard
        if self.path == "/" or self.path == "":
            self.send_response(302)
            self.send_header("Location", "/dashboard.html")
            self.end_headers()
            return

        # API endpoint for posts data
        if self.path == "/api/posts":
            self.send_json_response()
            return

        # Health check
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "time": datetime.now().isoformat(),
                "interval_minutes": SCRAPE_INTERVAL // 60
            }).encode())
            return

        # Serve static files
        super().do_GET()

    def send_json_response(self):
        db_path = BASE_DIR / "data" / "posts.json"
        if db_path.exists():
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            # Convert absolute image paths to relative paths for web serving
            base_str = str(BASE_DIR)
            for post in db.get("posts", []):
                if post.get("generated_images"):
                    post["generated_images"] = [
                        p.replace(base_str + "/", "./") if p.startswith(base_str) else p
                        for p in post["generated_images"]
                    ]
            data = json.dumps(db, ensure_ascii=False)
        else:
            data = json.dumps({"posts": [], "last_updated": None})

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data.encode("utf-8"))

    def log_message(self, format, *args):
        # Quiet logging - only log errors
        if args and "404" in str(args[0]):
            super().log_message(format, *args)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "server"

    if command == "server":
        # Ensure data directory and initial DB exist
        (BASE_DIR / "data").mkdir(exist_ok=True)
        db_path = BASE_DIR / "data" / "posts.json"
        if not db_path.exists():
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump({"posts": [], "last_run": None, "stats": {"total": 0, "by_platform": {}, "by_category": {}}}, f)

        print(f"""
╔══════════════════════════════════════════════════╗
║   🤖 AI Content Scraper - Server Mode           ║
║                                                  ║
║   Dashboard:  http://0.0.0.0:{PORT}              ║
║   Scraping:   Every {SCRAPE_INTERVAL // 60} minutes                    ║
║   Status:     /health                            ║
╚══════════════════════════════════════════════════╝
""")

        # Start background scraper thread
        scraper_thread = threading.Thread(target=scheduled_scraper, daemon=True)
        scraper_thread.start()

        # Start web server (main thread)
        os.chdir(str(BASE_DIR))
        with http.server.HTTPServer(("0.0.0.0", PORT), DashboardHandler) as httpd:
            print(f"🌐 Dashboard serving on port {PORT}...")
            httpd.serve_forever()

    elif command == "full":
        run_pipeline()

    elif command == "scrape":
        from scraper import run_scraper
        run_scraper()

    elif command == "rewrite":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        from hebrew_rewriter import rewrite_pending_posts
        rewrite_pending_posts(limit=limit)

    elif command == "generate":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        from image_generator import generate_pending_images
        generate_pending_images(limit=limit)

    elif command == "telegram":
        tg_cmd = sys.argv[2] if len(sys.argv) > 2 else "digest"
        os.system(f"{sys.executable} telegram_bot.py {tg_cmd}")

    else:
        print("""
🤖 AI Content Scraper - Usage:

  python run.py server     - Start dashboard + scheduled scraping (default)
  python run.py full       - Run full pipeline once (scrape + rewrite + notify)
  python run.py scrape     - Only scrape new posts
  python run.py rewrite    - Only rewrite pending posts to Hebrew
  python run.py rewrite 20 - Rewrite up to 20 posts
  python run.py generate   - Generate Hebrew carousel images
  python run.py generate 5 - Generate up to 5 carousels
  python run.py telegram   - Send Telegram digest
        """)


if __name__ == "__main__":
    main()

"""
AI Content Scraper - Main Runner
Run the full pipeline: Scrape → Categorize → Rewrite → Notify
"""

import sys
import os

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "full"

    if command == "full":
        print("\n🚀 Running full pipeline...\n")

        # Step 1: Scrape
        from scraper import run_scraper
        new_posts = run_scraper()

        # Step 2: Rewrite to Hebrew
        if new_posts > 0:
            from hebrew_rewriter import rewrite_pending_posts
            rewrite_pending_posts(limit=new_posts)

        # Step 3: Send Telegram digest
        os.system(f"{sys.executable} telegram_bot.py digest")

    elif command == "scrape":
        from scraper import run_scraper
        run_scraper()

    elif command == "rewrite":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        from hebrew_rewriter import rewrite_pending_posts
        rewrite_pending_posts(limit=limit)

    elif command == "telegram":
        tg_cmd = sys.argv[2] if len(sys.argv) > 2 else "digest"
        os.system(f"{sys.executable} telegram_bot.py {tg_cmd}")

    elif command == "dashboard":
        import http.server
        import webbrowser
        port = 8080
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        print(f"🌐 Dashboard running at http://localhost:{port}")
        print("   Press Ctrl+C to stop\n")
        webbrowser.open(f"http://localhost:{port}/dashboard.html")
        handler = http.server.SimpleHTTPRequestHandler
        with http.server.HTTPServer(("", port), handler) as httpd:
            httpd.serve_forever()

    else:
        print("""
🤖 AI Content Scraper - Usage:

  python run.py full       - Run full pipeline (scrape + rewrite + notify)
  python run.py scrape     - Only scrape new posts
  python run.py rewrite    - Only rewrite pending posts to Hebrew
  python run.py rewrite 20 - Rewrite up to 20 posts
  python run.py telegram   - Send Telegram digest
  python run.py dashboard  - Open the dashboard in browser
        """)


if __name__ == "__main__":
    main()

# AI Content Scraper - Setup Guide

## מה המערכת עושה

מערכת אוטומטית שסורקת תוכן על AI, עיצוב UI/UX ובניית אתרים מ-3 פלטפורמות, מקטלגת הכל, שולחת התראות לטלגרם, ומייצרת גרסאות בעברית ישראלית.

## מבנה הפרויקט

```
ai-content-scraper/
├── config.json          # הגדרות - API keys, מילות חיפוש, קטגוריות
├── run.py               # Runner ראשי - מריץ את כל הפייפליין
├── scraper.py           # סקרייפר Apify - Instagram, LinkedIn, TikTok
├── hebrew_rewriter.py   # שכתוב לעברית עם Nano Banana MCP
├── telegram_bot.py      # בוט טלגרם - התראות וסיכומים
├── dashboard.html       # דשבורד - ממשק צפייה וניהול
├── setup.md             # המדריך הזה
└── data/
    ├── posts.json       # מאגר הפוסטים (נוצר אוטומטית)
    └── images/          # תמונות שהורדו (נוצר אוטומטית)
```

## שלב 1: התקנות

```bash
pip install apify-client requests
```

## שלב 2: הגדרת Apify

1. היכנס ל-[apify.com](https://apify.com) עם החשבון שלך
2. לך ל-Settings → Integrations → API Token
3. העתק את ה-Token
4. פתח את `config.json` ושנה:

```json
"apify": {
    "token": "apify_api_XXXXXXXXXXXXX"
}
```

### Actors נדרשים ב-Apify

ודא שיש לך גישה ל-Actors הבאים (חינמיים / freemium):

| פלטפורמה | Actor | קישור |
|-----------|-------|-------|
| Instagram | `apify/instagram-scraper` | [Apify Store](https://apify.com/apify/instagram-scraper) |
| LinkedIn | `curious_coder/linkedin-post-search-scraper` | [Apify Store](https://apify.com/curious_coder/linkedin-post-search-scraper) |
| TikTok | `clockworks/tiktok-scraper` | [Apify Store](https://apify.com/clockworks/tiktok-scraper) |

> אם אתה מעדיף Actors אחרים, שנה את שמות ה-Actors ב-`config.json`

## שלב 3: הגדרת בוט טלגרם

1. פתח טלגרם ודבר עם [@BotFather](https://t.me/botfather)
2. שלח `/newbot` ועקוב אחרי ההוראות
3. קבל את ה-Bot Token
4. כדי לקבל את ה-Chat ID שלך:
   - שלח הודעה לבוט
   - פתח: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - חפש את `"chat":{"id": XXXXXXX}`
5. עדכן ב-`config.json`:

```json
"telegram": {
    "bot_token": "7123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxx",
    "chat_id": "123456789"
}
```

## שלב 4: הגדרת Nano Banana MCP (שכתוב לעברית)

### אופציה א' - Nano Banana API

```bash
export NANO_BANANA_URL="https://api.nanobanana.com/v1/chat"
export NANO_BANANA_API_KEY="nb_xxxxxxxxxxxxx"
```

### אופציה ב' - Anthropic API (Fallback)

```bash
export ANTHROPIC_API_KEY="sk-ant-xxxxxxxxxxxxx"
```

## שלב 5: התאמת מילות חיפוש

פתח את `config.json` ושנה את:

- `keywords` - מילות חיפוש כלליות
- `hashtags_instagram` - האשטגים לאינסטגרם
- `profiles_to_track` - פרופילים ספציפיים לעקוב
- `categories` - קטגוריות ומילות מפתח לסיווג אוטומטי

## הרצה

### פייפליין מלא

```bash
python run.py full
```

### רק סריקה

```bash
python run.py scrape
```

### רק שכתוב לעברית (10 פוסטים)

```bash
python run.py rewrite 10
```

### שליחת סיכום לטלגרם

```bash
python run.py telegram digest      # סיכום יומי
python run.py telegram categories  # פילוח לפי קטגוריות
python run.py telegram top         # Top 5 פוסטים
python run.py telegram hebrew      # פוסטים שתורגמו לעברית
```

### פתיחת דשבורד

```bash
python run.py dashboard
```

## תזמון אוטומטי (Cron)

להרצה כל 6 שעות:

```bash
crontab -e
```

הוסף:

```
0 */6 * * * cd /path/to/ai-content-scraper && python run.py full >> logs/cron.log 2>&1
```

## הדשבורד

הדשבורד הוא קובץ HTML יחיד שרץ בדפדפן. הוא:

- מציג את כל הפוסטים בממשק מסודר עם קטגוריות
- מאפשר סינון לפי פלטפורמה, קטגוריה, חיפוש חופשי
- מציג סטטיסטיקות בזמן אמת
- מראה גרסאות בעברית
- תומך בייצוא לJSON
- עיצוב Dark Mode מודרני

> בפעם הראשונה הוא ייטען עם נתוני דמו. אחרי ההרצה הראשונה של הסקרייפר, הוא ייטען נתונים אמיתיים מ-`data/posts.json`

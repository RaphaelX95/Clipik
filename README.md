# קליפיק — פלטפורמת יצירת סרטוני AI למוצרים

אפליקציית דפדפן ליצירת סרטוני מוצר/UGC באמצעות בינה מלאכותית. המשתמש מעלה תמונה/קישור למוצר, בוחר סגנון ומשך, ומקבל סרטון איכותי שנוצר בענן.

## תכונות עיקריות

- ממשק RTL בעברית, מותאם למובייל
- חבילות טוקנים: חינם初次 + חבילות 3/5/10 סרטונים + חבילות גדולות
- תשלום דינמי דרך iCount
- Kling 4.0 דרך UnificAlly ליצירת וידאו, בחירה של 720p או 1080p
- תיקון אוטומטי של טקסט עברי לפני קריינות
- מניעת חיובים כפולים במטמון 5 דקות
- מדור טיפים לפרסום מוצרים ברשתות (SEO)
- 14 טסטים אוטומטיים

## טכנולוגיות

- Frontend: HTML/CSS/JavaScript (RTL)
- Backend: Python HTTP server
- וידאו: UnificAlly (kuaishou/kling-4.0-video)
- תשלומים: iCount
- בדיקות: unittest

## הפעלה מקומית

### דרישות
- Python 3.10+
- uv (מנהל תלויות)
- מפתחות API: `UNIFICALLY_API_KEY`, `ICOUNT_CID`, `ICOUNT_USER`, `ICOUNT_PASS`, `ICOUNT_PAGE_ID`

### התקנה

```bash
# שכפול הפרויקט
git clone https://github.com/RaphaelX95/Clipik.git
cd Clipik

# התקנת תלויות
uv sync

# הגדרת משתני סביבה
cp .env.example .env
# ערכו את .env עם המפתחות שלכם

# הפעלת השרת
uv run python server.py
```

השרת יעלה על `http://127.0.0.1:8765`.

### בדיקות

```bash
uv run python -m unittest discover -s tests -v
```

## פריסה לפרודקשן

ראה `DEPLOY.md` for הוראות פריסה מלאות.

### משתני סביבה נדרשים

```env
UNIFICALLY_API_KEY=
ICOUNT_CID=
ICOUNT_USER=
ICOUNT_PASS=
ICOUNT_PAGE_ID=14
BASE_URL=https://clipik.pro
PORT=8765
```

## מבנה הפרויקט

```
├── index.html          # ממשק ראשי
├── packages.html       # חבילות טוקנים
├── tips.html          # מדור טיפים לפרסום
├── server.py          # שרת HTTP + API
├── fal_provider.py    # עזרי תסריט ופרומפט
├── unifically_provider.py # מתאם Kling 4.0 דרך UnificAlly
├── deploy.py          # סקריפט פריסה
├── sitemap.xml        # מפת אתר
├── robots.txt         # הגבלות גירדפלג
├── tests/             # בדיקות אוטומטיות
└── .env.example       # תבנית משתני סביבה
```

## API Endpoints

- `GET /api/health` - בדיקת בריאות
- `GET /api/fal/status` - סטטוס ספק וידאו
- `GET /api/fal/estimate?duration=15&resolution=720p` - הערכת עלות טוקנים
- `POST /api/generations` - יצירת סרטון
- `POST /api/icount/create-payment` - יצירת תשלום
- `GET /api/users/me` - פרטי משתמש נוכחי

## עלות

- סרטון 15 שניות ב-720p ≈ $1.70, ב-1080p ≈ $2.55 (UnificAlly, לפני ניסיונות חוזרים)
- 1080p עולה פי 1.5 מ-720p, ולכן גם הטוקנים מוכפלים ב-1.5
- מחיר טוקן: ₪1.96 (כ-פי 2 מהעלות, לפי שער דולר ₪3.45)
- חבילות: 6 טוקנים חינם初次, 3/5/10 סרטונים, סטארטאפ/סטנדרט/פרימיום/אולטרה

## רישיון

 proprietary - כל הזכויות שמורות © 2026 קליפיק

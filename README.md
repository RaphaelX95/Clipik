# קליפיק — פלטפורמת יצירת סרטוני AI למוצרים

אפליקציית דפדפן ליצירת סרטוני מוצר/UGC באמצעות בינה מלאכותית. המשתמש מעלה תמונה/קישור למוצר, בוחר סגנון ומשך, ומקבל סרטון איכותי שנוצר בענן.

## תכונות עיקריות

- ממשק RTL בעברית, מותאם למובייל
- חבילות טוקנים: חינם初次 + חבילות 3/5/10 סרטונים + חבילות גדולות
- תשלום דינמי דרך iCount
- שים Kling 4.0 (fal.ai) ליצירת וידאו
- תיקון אוטומטי של טקסט עברי לפני קריינות
- מניעת חיובים כפולים במטמון 5 דקות
- מדור טיפים לפרסום מוצרים ברשתות (SEO)
- 14 טסטים אוטומטיים

## טכנולוגיות

- Frontend: HTML/CSS/JavaScript (RTL)
- Backend: Python HTTP server
- וידאו: fal.ai Kling 4.0
- תשלומים: iCount
- בדיקות: unittest

## הפעלה מקומית

### דרישות
- Python 3.10+
- uv (מנהל תלויות)
- מפתחות API: `FAL_KEY`, `ICOUNT_CID`, `ICOUNT_USER`, `ICOUNT_PASS`, `ICOUNT_PAGE_ID`

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
FAL_KEY=
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
├── fal_provider.py    # מתאם Kling 4.0
├── deploy.py          # סקריפט פריסה
├── sitemap.xml        # מפת אתר
├── robots.txt         # הגבלות גירדפלג
├── tests/             # בדיקות אוטומטיות
└── .env.example       # תבנית משתני סביבה
```

## API Endpoints

- `GET /api/health` - בדיקת בריאות
- `GET /api/fal/status` - סטטוס ספק וידאו
- `GET /api/fal/estimate?duration=15` - הערכת עלות טוקנים
- `POST /api/generations` - יצירת סרטון
- `POST /api/icount/create-payment` - יצירת תשלום
- `GET /api/users/me` - פרטי משתמש נוכחי

## עלות

- סרטון 15 שניות ≈ $1.67 (fal.ai)
- מחיר טוקן: ₪2.70 (רווח 50%)
- חבילות: 6 טוקנים חינם初次, 3/5/10 סרטונים, סטארטאפ/סטנדרט/פרימיום/אולטרה

## רישיון

 proprietary - כל הזכויות שמורות © 2026 קליפיק

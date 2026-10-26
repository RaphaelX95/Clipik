# קליפיק - הפעלת האתר בשרת אמיתי

## שלבי הפריסה

### 1. קניית דומיין
- קנו דומיין (למשל: `klipik.co.il`) מ-registrar כמו:
  - GoDaddy
  - Namecheap
  - Cloudflare Registrar
  - או ספק ישראלי

### 2. בחרו אחסון
**אפשרויותzos:**
- **VPS:** DigitalOcean, Linode, AWS EC2 (~$5/חודש)
- **Shared hosting:** IsraStack, Factor, Nana10 (~₪20-50/חודש)
- **Static + Serverless:** Vercel/Netlify לדפים + Render/Railway לשרת Python

**מומלץ לסטארטאפ:** Static hosting (Vercel/Netlify) + Railway/Render לשרת

### 3. העלאת הקבצים
העלו את כל הקבצים בתיקייה אחת לשרת:
```
index.html
packages.html
tips.html
payment_success.html
payment_failure.html
payment_cancel.html
sitemap.xml
robots.txt
server.py
fal_provider.py
users.json
transactions.json
projects.json
```

### 4. הגדרת משתני סביבה
הגדירו ב-`.env` או בממשק השרת:
```env
FAL_KEY=fal_sk_...
ICOUNT_CID=...
ICOUNT_USER=...
ICOUNT_PASS=...
ICOUNT_PAGE_ID=14
BASE_URL=https://klipik.co.il
PORT=8765
```

### 5. עדכון URLs בפריסה
הריצו סקריפט העדכון לפני העלאה:
```bash
python deploy.py https://klipik.co.il
```

### 6. הפעלת השרת
```bash
# עדכנו uv אם צריך
pip install uv

# הפעילו שרת
uv run python server.py
```

### 7. הגדרת Reverse Proxy (אם רוצים שלא יראו את ה-Port)
בתמש Nginx/Apache, העבירו трафיק מפורט 80/443 לפורט 8765.

### 8. Google Search Console
1. גשו ל [Google Search Console](https://search.google.com/search-console)
2. הוסיפו דומיין: `klipik.co.il`
3. אוירו ownership:
   - **קובץ HTML:** הורידו קובץ אימות והעלו אותו לתיקיית האתר
   - **DNS TXT:** הוסיפו רשומה בדDNS
   - **Meta tag:** הוסיפו tag ל-index.html
4. שלחו sitemap.xml: `https://klipik.co.il/sitemap.xml`

### 9. תמונות עם alt text
הוסיפו תמונות למוצרים עם `alt` text מפורט:
```html
<img src="product.jpg" alt="שפת סינון למים - מסוג Carbon">
```

### 10. קישורים חיצוניים
צרו קישורים לרשתות חברתיות:
- Facebook business page
- Instagram
- TikTok
- LinkedIn

**טיפ:** פרסמו סרטוני UGC שאתם יוצרים בעצמכם כדי לקבל תנועה.

## בדיקה אחרי פריסה
- [ ] האתר נגיש בדומיין
- [ ] https עובד (SSL)
- [ ] robots.txt נגיש
- [ ] sitemap.xml נגיש
- [ ] Google Search Console אימות
- [ ]=iCount redirect URLs עובדים
- [ ] סרטון ראשון חינם עובד

## תמיכה
פנו ל-אימייל או WhatsApp לתמיכה טכנית.

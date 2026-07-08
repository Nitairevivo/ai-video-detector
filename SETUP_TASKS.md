# ✅ משימות ההגדרה של ניתאי — מדריך קליקים מדויק (~40 דקות סה"כ)

*כל משימה כאן דורשת חשבון אישי שלך — לכן רק אתה. כל השאר כבר קוד ורץ.*

---

## 1. 🎯 סרטונים לבנצ'מרק (הכי חשוב — 30-40 דק')

**למה רק אתה:** הרשת של סביבת העבודה חוסמת הורדות וידאו; צריך את הטלפון שלך (IP ביתי).

1. פתח את `tests/COLLECTION_PLAN.md` — יש שם רשימה מדויקת של מה לאסוף
2. בטלפון: טיקטוק/יוטיוב → סרטון → Share → שמור/הורד (או Share → VerifAI → שמור)
3. שים הכל בתיקייה אחת במחשב + קובץ `manifest.csv`:
   ```csv
   filename,label,platform,category
   kling_dragon.mp4,ai,tiktok,kling
   flour_challenge.mp4,real,tiktok,chaotic
   ```
4. תגיד לי "יש סרטונים" — ואני מריץ, מנתח כשלים ומתקן.
   (או בעצמך: `python tests/real_benchmark.py <תיקייה> --manifest manifest.csv`)

**מתחילים מ-40 סרטונים (20/20) — זה מספיק לריצה ראשונה.**

---

## 2. 🌐 VERCEL_TOKEN — האתר לא מתעדכן בלעדיו (5 דק')

1. https://vercel.com/account/tokens → **Create Token** (שם: `github-deploy`, Scope: Full)
2. העתק את הטוקן
3. https://github.com/Nitairevivo/ai-video-detector/settings/secrets/actions → מצא `VERCEL_TOKEN` → **Update** → הדבק
4. אחר כך ב-Actions → Deploy → **Re-run** על הריצה האחרונה

---

## 3. 🎬 PEXELS_API_KEY — מדליק אימון-ענן אוטומטי (5 דק')

1. https://www.pexels.com/api/ → הרשמה חינם → העתק את המפתח
2. https://github.com/Nitairevivo/ai-video-detector/settings/secrets/actions → **New repository secret** → שם: `PEXELS_API_KEY`, ערך: המפתח
3. זהו — האימון ירוץ אוטומטית שני+חמישי ב-03:00 UTC (או ידנית: Actions → Cloud Training → Run workflow)

---

## 4. 📱 וואטסאפ בוט — Meta Developer (20 דק')

1. https://developers.facebook.com → **My Apps** → **Create App** → סוג: Business
2. בתוך האפליקציה: **Add Product** → WhatsApp → Set up (מקבל מספר טסט חינם)
3. מתוך WhatsApp → API Setup העתק: **Temporary access token** + **Phone number ID**
4. ב-Railway (השירות של ה-API) → Variables, הוסף:
   - `WHATSAPP_TOKEN` = הטוקן
   - `WHATSAPP_PHONE_NUMBER_ID` = ה-ID
   - `WHATSAPP_VERIFY_TOKEN` = כל סיסמה שתבחר (למשל `verifai-hook-2026`)
5. חזרה ב-Meta: WhatsApp → Configuration → **Webhook**:
   - Callback URL: `https://ai-video-detector-production-a305.up.railway.app/whatsapp/webhook`
   - Verify token: אותה סיסמה מסעיף 4
   - Subscribe ל-**messages**
6. שלח סרטון למספר הטסט — אמור לחזור פסק דין בעברית 🎉
   (לטוקן קבוע: Business Settings → System Users → צור טוקן permanent)

---

## 5. 🔍 SynthID Detector waitlist (5 דק')

1. https://deepmind.google/models/synthid/ → **SynthID Detector** → Join waitlist
2. הרשם עם המייל שלך (עדיף להציג את עצמך כ-developer/researcher בתחום זיהוי AI)
3. כשתתקבל גישה — תגיד לי ואבנה את האינטגרציה תוך יום

---

## 6. 🚨 SENTRY_DSN — התראות שגיאה (5 דק')

1. https://sentry.io → חשבון חינם → Create Project → Platform: FastAPI
2. העתק את ה-DSN (`https://...ingest.sentry.io/...`)
3. Railway → Variables → `SENTRY_DSN` = ה-DSN
4. זהו — הקוד כבר מוכן, נדלק אוטומטית

---

## 7. ⚙️ (רשות, 1 דק') Auto-merge

https://github.com/Nitairevivo/ai-video-detector/settings → General → Pull Requests → ✅ **Allow auto-merge**
→ מרגע זה המיזוגים שלי נכנסים אוטומטית ברגע שה-CI ירוק.

---

*כל משימה שהושלמה — תגיד לי ואני מיד מחבר/מריץ/ממשיך את הצד שלי.*

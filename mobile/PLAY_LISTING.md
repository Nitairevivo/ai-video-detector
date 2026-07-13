# VerifAI — Google Play listing (Hebrew primary)

Ready to paste into Play Console. Character limits noted; all within Google's caps
(title ≤30, short ≤80, full ≤4000).

---

## Title (25/30)
```
VerifAI – זיהוי סרטוני AI
```

## Short description (66/80)
```
בדוק אם סרטון או תמונה נוצרו ב-AI, והגן על עצמך ועל ההורים מהונאות
```

## Full description
```
בעידן ה-AI, כל סרטון יכול להיות מזויף.

סרטון "השקעה" עם דמות מוכרת. הודעת וידאו מ"חבר" בוואטסאפ. "מוכר" ביד2 ששולח סרטון של המוצר. כולם נראים אמיתיים — ובדיוק ככה מרמים אנשים, במיוחד מבוגרים, ומוציאים מהם אלפי שקלים.

VerifAI אומר לך תוך שניות מה אמיתי ומה נוצר במכונה.

━━━━━━━━━━━━━━━
🛡️ 3 דרכים לבדוק
━━━━━━━━━━━━━━━

• שתף → VerifAI — פתח כל סרטון או תמונה, לחץ "שתף", ובחר VerifAI. הדרך הכי אמינה, תמיד עובדת.
• הכפתור הצף — כפתור קטן שמופיע מעל אפליקציות אחרות (TikTok, וואטסאפ, אינסטגרם ועוד). לחיצה אחת בודקת את מה שאתה צופה בו, בלי לצאת מהאפליקציה.
• הדבק קישור — הדבק קישור לסרטון וקבל תשובה.

━━━━━━━━━━━━━━━
🔍 איך VerifAI יודע?
━━━━━━━━━━━━━━━

לא ניחוש. VerifAI קורא את הראיות שאי אפשר לזייף:

• חתימות של כלי-AI (Sora, Veo, Midjourney) ואישורי C2PA שחבויים בקובץ.
• תוויות ה-AI הרשמיות של TikTok, YouTube, Instagram ו-X.
• מודל ניתוח חזותי מכויל — עם דגש על אפס אזעקות שווא.

━━━━━━━━━━━━━━━
💜 למה VerifAI
━━━━━━━━━━━━━━━

• עברית מלאה — נבנה בשביל ישראל.
• פשוט מספיק להורים ולסבים — התקן להם, ותגן עליהם מהונאה הבאה.
• עובד בתוך כל אפליקציה, כולל וואטסאפ, טלגרם ואפליקציות היכרויות.
• 10 בדיקות חינם בכל חודש. שדרוג ל-Pro לבדיקות ללא הגבלה.

לפני שאתה מאמין לסרטון — תבדוק. הורד את VerifAI היום.
```

## What's new (release notes)
```
• "שתף → VerifAI" עכשיו הדרך הראשית — הכי מהירה ואמינה.
• זיהוי גם בתוך וואטסאפ, טלגרם ואפליקציות היכרויות.
• מדריך פתרון תקלות והדגמה חיה בתוך האפליקציה.
```

---

## ⚠️ Accessibility disclosure (REQUIRED by Google Play)

The app uses an AccessibilityService (to show the floating button inside other
apps and read the current video). Google Play **rejects** accessibility apps
without a clear justification. You must:

1. In Play Console → App content → **declare the accessibility use** and paste a
   justification like the one below.
2. Show a **prominent in-app disclosure** before enabling it (the onboarding/guide
   already explains it — make sure the wording matches).

**Justification text (paste in Play Console):**
```
VerifAI uses the AccessibilityService solely to power its user-facing "floating
button" feature: when the user explicitly enables it, the service detects which
app is in the foreground so the button can appear over supported apps, and — only
when the user taps the button — reads the currently visible video's share link to
check whether it is AI-generated. The service does not collect, log, or transmit
any screen content, personal data, or keystrokes. It is fully optional; all core
functionality works via Share and paste-a-link without it.
```

**Note:** If Play review pushes back on the accessibility use (it sometimes does
for non-disability apps), ship the **Play build variant** (`EXPO_PUBLIC_PLAY_BUILD=1`)
which has NO accessibility service — the floating button then works via the
screen-capture path instead. Keep the full sideload APK for direct distribution.

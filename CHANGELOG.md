# VerifAI — What's New

## 2026-07-13 — Model & detection improvements

- Video detector now at 0.997 AUC with a 0.3% false-positive rate (trained on 5,164 videos).
- Image detector trained on 3,249 samples (AUC 0.852).
- Cover DeepAction generators + auto-label pulls only AI when real-saturated.
- Cap real:AI imbalance so the AI signal isn't drowned.
- Poison-proof on-ramp for generator diversity.
- Hard-sample mining to target the recall gap.

## 2026-07-12 — Model & detection improvements

- Video detector now at 0.956 AUC with a 2.6% false-positive rate (trained on 4,530 videos).
- Image detector trained on 1,749 samples (AUC 1.000).
- Detect-url: never analyze a non-video download (false-positive guard).
- Fix mobile OTA gate: expo export needs a project-relative output dir.
- Fix 'everything is 6% real': restore Gemini's time budget.
- Fix mobile startup crash: make OTA safe, not a brick vector.

## 2026-07-12 — עיצוב חדש + תיקוני הכפתור הצף

- עיצוב מחדש מלא: RTL אמיתי, מסך תוצאה חדש עם פס ביטחון והסברים, מרכז בקרה שמראה אילו הרשאות פעילות.
- הכפתור הצף תוקן: בודק את הסרטון שעל המסך (לא קישור ישן מהלוח), לחיצה שנייה מבטלת, ואפשר לגרור אותו.
- היסטוריית הבדיקות נשמרת גם אחרי סגירת האפליקציה.
- בדיקת תמונות: שתפו תמונה מכל אפליקציה אל VerifAI.
- תיבת הדבקת קישור חדשה — הדבק ובדוק בלחיצה אחת.

## 2026-07-11 — Model & detection improvements

- Video detector now at 0.975 AUC with a 2.7% false-positive rate (trained on 882 videos).
- Image detector trained on 1,249 samples (AUC 1.000).
- Add user's real media as permanent training seed (69 images + 4 videos).
- Fix image false-positive: tool tokens matched in compressed pixel bytes.
- Add gated auto-promote: ship nightly-trained models to production safely.
- Detect AI-generated images too (code-first, like the video engine).

## 2026-07-10 — Model & detection improvements

- Video detector now at 0.975 AUC with a 2.7% false-positive rate (trained on 882 videos).
- Add user's real media as permanent training seed (69 images + 4 videos).
- Fix image false-positive: tool tokens matched in compressed pixel bytes.
- Add gated auto-promote: ship nightly-trained models to production safely.
- Detect AI-generated images too (code-first, like the video engine).

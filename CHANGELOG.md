# VerifAI — What's New

## 2026-07-12 — Model & detection improvements

- Video detector now at 0.961 AUC (trained on 1,047 videos).
- Image detector trained on 1,749 samples (AUC 1.000).
- Fix mobile OTA gate: expo export needs a project-relative output dir.
- Fix 'everything is 6% real': restore Gemini's time budget.
- Fix mobile startup crash: make OTA safe, not a brick vector.
- Fix miscalibration on class-ordered data: FPR 7.6% -> 0.4%.

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

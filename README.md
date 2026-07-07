# VerifAI — AI Video Detector

**Detects whether a video was AI-generated (Sora, Veo, Kling, Runway, Pika, Hailuo…) by reading the evidence platforms can't erase.**

Platforms like TikTok and Instagram re-encode every upload and strip the file's original metadata — so VerifAI layers three independent kinds of evidence:

1. **File forensics** — cryptographic verification of C2PA Content Credentials, AI-tool metadata signatures, proprietary MP4 boxes and codec/bitstream fingerprints (30+ tools recognized).
2. **Platform intelligence** — the platform's *own* AI-disclosure labels (TikTok AIGC, YouTube "Altered or synthetic content", Meta "AI info"), read from page/API JSON where they survive transcoding.
3. **Vision ensemble** — Gemini temporal-pair analysis fused in log-odds space with a frame model, frequency/motion analysis and audio fingerprinting. Probabilities are calibrated (isotonic), and a lone layer can never flip a verdict by itself.

Current model: Gradient Boosting over ~49 signals, 882 labeled samples, **cross-validated AUC 0.975, precision 96.5%, FPR 2.7%** (5-fold CV; blind real-world benchmark in progress — see `tests/COLLECTION_PLAN.md`).

## Products on this engine

| Surface | Where | Notes |
|---|---|---|
| REST API | FastAPI on Railway | `/detect`, `/detect-url`, `/detect-batch` (up to 1000 URLs), `/detect-frame`, Stripe billing, rate-limited, `/health` |
| Telegram bot | in-process with the API | receives the **original file bytes** — the most accurate path; supports self-hosted Bot API (2GB files) |
| WhatsApp bot | `/whatsapp/webhook` | Meta Business Cloud API; same engine, Hebrew replies |
| Web app | Next.js on Vercel | drag-drop / URL check, forensics breakdown panel, API dashboard with key rotation |
| Mobile app | Expo (Android/iOS) | Share-intent, gallery watcher, floating overlay over TikTok, phone-side download (residential IP bypasses CDN blocks) |
| Chrome extension | MV3 | verdict badges on 10 platforms |
| SDKs | `sdk/python`, `sdk/javascript` | publish-ready packages, expose the `explanation` audit payload |

## Quickstart

```bash
pip install -r requirements.txt          # needs ffmpeg installed (apt install ffmpeg)
python main.py detect video.mp4          # CLI detection
python main.py serve                     # API on :8000  (docs at /docs)
python -m pytest tests/ -q               # test suite
```

Detect via API:

```bash
curl -X POST localhost:8000/detect-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.tiktok.com/@user/video/123"}'
```

Every response includes an `explanation` object: deciding layer, per-layer scores, provenance flags (C2PA presence/claims, metadata stripped, platform re-encode) and caveats.

## Repository map

```
analyzer/          detection engine (metadata, C2PA, container, codec, platform labels,
                   TikTok resolver, Gemini, visual/frequency/motion/audio, ensemble)
models/            GradientBoosting classifier (calibrated) + trained artifact
api/               FastAPI server, Telegram bot, WhatsApp bot, billing, key DB
web/               Next.js app (landing, detector, dashboard, /privacy)
mobile/            Expo app v1.4.0 (he/en)
chrome-extension/  MV3 extension
sdk/               Python + JavaScript client SDKs
tests/             unit tests + real-world benchmark runner (real_benchmark.py)
train_forever.py   continuous training loop (cloud-ready; .github/workflows/train.yml)
ROADMAP.md         phased plan to enterprise-ready, with live status
PROJECT_STATUS.md  full architecture + provenance strategy write-up
```

## Environment

See `.env.example` — Gemini key for the vision layer, optional Telegram/WhatsApp tokens, Stripe billing, Sentry DSN, Pexels key for training.

## Operating principles

- **No statistical guessing where evidence exists**: signed C2PA or a platform label decides immediately (0.93-0.99); statistics only fill the gap.
- **False positives are the worst failure**: single-witness rule, camera-origin guard and probability calibration all bias toward *not* crying wolf on real footage.
- **Privacy by design**: videos are deleted the moment analysis completes; only numeric feature vectors are kept when a user explicitly submits a training sample. See `/privacy`.

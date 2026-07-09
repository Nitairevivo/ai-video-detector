# VerifAI — Quickstart (הרצה מהירה)

VerifAI reads *the code behind the video* — file metadata, C2PA credentials,
open provenance markers (IPTC DigitalSourceType), container/codec fingerprints
and platform AI-labels — to decide if a video is AI-generated. No frame decode
on the fast path, so it answers in ~1 second.

---

## 1. Run the API (one command)

```bash
./run.sh
```

That's it. `run.sh` creates a virtualenv, installs the Python deps, and starts
the API on **http://localhost:8000**. First run takes a minute (it downloads
the deps); after that it's instant.

Prefer to do it by hand?

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py serve            # → http://localhost:8000
```

Open **http://localhost:8000/docs** for the interactive API (Swagger).

### Try it — the code-first fast path (~1s, no frame decode)

```bash
# health check
curl http://localhost:8000/health

# analyze a local video file, code-first
curl -F "file=@/path/to/video.mp4" "http://localhost:8000/detect?mode=fast"
```

You get back a JSON verdict (`real` / `ai_generated` / `ai_edited`), a
confidence, and an `explanation` object with the deciding layer, provenance
markers (C2PA / IPTC / AI-tool / camera) and per-layer scores.

---

## 2. Run the website (the designed UI)

```bash
cd web
npm install
npm run dev                     # → http://localhost:3000
```

The landing page, the live demo, `/accuracy`, `/privacy` and the B2B
`/dashboard` are all there — premium dark theme (aurora background,
glassmorphism, the forensics report with the frame timeline).

To point the site at your local API instead of the hosted one, set
`NEXT_PUBLIC_API_URL=http://localhost:8000` before `npm run dev`.

---

## 3. Run the tests (prove it works)

```bash
pip install -r requirements.txt
python -m pytest tests/ -q       # 55 tests
```

---

## What's in here

| Path | What it is |
|------|-----------|
| `analyzer/` | the detection engine (metadata, C2PA, IPTC, container, codec, visual) |
| `api/` | FastAPI server + Telegram bot + WhatsApp bot |
| `web/` | Next.js website (the designed UI) |
| `mobile/`, `mobile-src/` | the React-Native / Expo app |
| `sdk/` | Python + JS SDKs |
| `models/` | the trained classifier (`trained_model.joblib`) + frame model |
| `tests/` | test suite + the real-world benchmark |
| `.github/workflows/` | CI, deploy, nightly train, weekly auto-benchmark |

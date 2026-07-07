"""
FastAPI server — upload a video, get AI detection results in seconds.
"""
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Body, Request, Header, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from starlette.concurrency import run_in_threadpool

from analyzer import extract_features
from models.classifier import get_classifier
from api.database import (init_db, create_key, lookup_key, record_request,
                          record_request_by_id, rotate_key, get_key_by_email, TIERS)
from api.billing import create_checkout_session, handle_webhook

# Error monitoring — active only when SENTRY_DSN is set (roadmap 4.2)
if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], traces_sample_rate=0.1)
        print("[startup] Sentry error monitoring enabled")
    except Exception as e:
        print(f"[startup] Sentry init failed: {e}")

# Init DB on startup
init_db()

# Build frame visual model if not present (runs once at startup, ~2 min)
import threading
def _build_frame_model_bg():
    try:
        from analyzer.build_frame_model import ensure_model
        ensure_model(verbose=True)
    except Exception as e:
        print(f"[startup] frame model build failed: {e}")
threading.Thread(target=_build_frame_model_bg, daemon=True).start()

# Run the Telegram bot in-process (long polling) when a token is configured.
# One Railway service then serves BOTH the API and the bot — no extra config.
def _run_telegram_bot_bg():
    try:
        if not os.environ.get("TELEGRAM_BOT_TOKEN", "").strip():
            return
        from api.telegram_bot import main as _tg_main
        print("[startup] launching Telegram bot…")
        _tg_main()
    except Exception as e:
        print(f"[startup] telegram bot stopped: {e}")
threading.Thread(target=_run_telegram_bot_bg, daemon=True).start()

app = FastAPI(
    title="VerifAI — AI Video Detector API",
    description=(
        "Detect AI-generated videos with three layers of evidence: "
        "cryptographic C2PA verification + file forensics, the platforms' own "
        "AI-disclosure labels, and a calibrated vision ensemble. "
        "Every response includes an `explanation` audit object. "
        "Videos are deleted immediately after analysis."
    ),
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# WhatsApp Business Cloud API webhook (active when WHATSAPP_* env vars are set)
from api.whatsapp_bot import router as _whatsapp_router
app.include_router(_whatsapp_router, tags=["whatsapp"])

# ─── Rate limiting ─────────────────────────────────────────────────────────────
# Per-IP limits on the expensive endpoints. Quotas already cap keyed usage;
# this stops anonymous floods (the web-app referer bypass is spoofable, so
# unauthenticated traffic must be bounded too).

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


def _client_ip(request: Request) -> str:
    # Railway/Vercel sit behind proxies — the real client is in X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ─── Observability ─────────────────────────────────────────────────────────────

import json as _obs_json
import time as _obs_time

_SERVER_STARTED_AT = _obs_time.time()


@app.middleware("http")
async def _access_log(request: Request, call_next):
    """One structured JSON log line per request — greppable in Railway logs."""
    t0 = _obs_time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # Health checks and docs would drown the log — skip them
        if request.url.path not in ("/", "/health", "/docs", "/openapi.json"):
            print(_obs_json.dumps({
                "evt": "request",
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "ms": round((_obs_time.perf_counter() - t0) * 1000),
            }))


@app.get("/health")
def health():
    """Liveness/readiness probe with component status — for uptime monitors."""
    classifier = get_classifier()
    meta = {}
    try:
        meta_path = Path(__file__).parent.parent / "models" / "trained_model_meta.json"
        meta = _obs_json.loads(meta_path.read_text())
    except Exception:
        pass
    return {
        "status": "ok",
        "uptime_s": round(_obs_time.time() - _SERVER_STARTED_AT),
        "model": {
            "trained": classifier.is_trained,
            "samples": meta.get("samples"),
            "cv_auc": meta.get("cv_auc_mean"),
            "trained_at": meta.get("trained_at"),
        },
        "gemini_enabled": bool(os.environ.get("GEMINI_API_KEY")),
        "telegram_bot": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
        "whatsapp_bot": all(os.environ.get(k, "").strip() for k in
                            ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_VERIFY_TOKEN")),
    }

# ─── API Key auth ──────────────────────────────────────────────────────────────

FREE_ENDPOINTS = {"/", "/register", "/docs", "/openapi.json", "/stripe/webhook"}

def get_api_key(request: Request, x_api_key: Optional[str] = Header(None)):
    """
    Validate API key from X-Api-Key header.
    Skips auth for public endpoints and for the web app's own requests
    (identified by Referer pointing to our Vercel domain).
    """
    if request.url.path in FREE_ENDPOINTS:
        return None

    # Allow our own web app to call without key
    referer = request.headers.get("referer", "")
    if "web-zeta-ecru-80.vercel.app" in referer or "localhost" in referer:
        return None

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Get a free key at https://web-zeta-ecru-80.vercel.app/dashboard",
            headers={"X-Api-Key-Docs": "https://web-zeta-ecru-80.vercel.app/dashboard"},
        )

    key = lookup_key(x_api_key)
    if not key:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    if key.over_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly limit reached ({key.monthly_limit} requests). Upgrade at https://web-zeta-ecru-80.vercel.app/dashboard",
        )

    record_request(x_api_key)
    return key

SUPPORTED_FORMATS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi'}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
# We only need the first 10MB for metadata + container analysis.
# Codec frame analysis (ffprobe) reads directly from disk and is already limited to 120 frames.
FAST_READ_BYTES = 10 * 1024 * 1024  # 10MB


@app.get("/")
def root():
    classifier = get_classifier()
    return {
        "status": "ok",
        "model_trained": classifier.is_trained,
        "gemini_enabled": bool(os.environ.get("GEMINI_API_KEY")),
        "supported_formats": list(SUPPORTED_FORMATS),
    }


@app.post("/detect")
@limiter.limit("30/minute")
async def detect(
    request: Request,
    file: UploadFile = File(...),
    deep: bool = False,
):
    """
    Analyze a video file for AI generation.
    deep=true: also runs visual + frequency analysis (~10s extra, better for re-encoded/stripped videos).
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format: {suffix}. Use: {SUPPORTED_FORMATS}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        chunk = await file.read(FAST_READ_BYTES)
        if not chunk:
            raise HTTPException(400, "Empty file")
        tmp.write(chunk)

    try:
        # Analysis takes 10-60s of CPU/IO — run it off the event loop so one
        # video doesn't freeze every other request on the server.
        payload = await run_in_threadpool(run_full_analysis, tmp_path, deep)
        payload["filename"] = file.filename
        payload["signals"] = payload.pop("_signals", {})
        return payload
    finally:
        os.unlink(tmp_path)


def run_full_analysis(tmp_path: str, deep: bool = True) -> dict:
    """
    Shared analysis pipeline: metadata/container features → Gemini-base ensemble
    (Gemini + visual + audio + frame-ML fused). Used by /detect, /detect-url
    and the Telegram bot.
    """
    from analyzer.ensemble import analyze_ensemble

    result = extract_features(tmp_path, deep=deep)
    classifier = get_classifier()
    ml_prob, _ = classifier.predict(result.feature_vector)

    ens = analyze_ensemble(tmp_path, result, ml_prob, use_gemini=True)

    signals = result.signals or {}
    return {
        "is_ai_generated": ens.verdict == "ai_generated",
        "verdict": ens.verdict,
        "confidence": round(ens.confidence, 4),
        "confidence_pct": f"{ens.confidence * 100:.1f}%",
        "ai_tool_detected": result.ai_tool,
        "edit_tool_detected": result.edit_tool,
        "detection_method": ens.method,
        "deep_analysis_ran": bool(signals.get("freq_analyzed") or signals.get("visual_analyzed")),
        "ensemble_layers": ens.layers,
        "gemini_reason": ens.gemini_reason,
        # Audit-grade breakdown of how the verdict was reached — what
        # enterprise integrations log next to the verdict (roadmap 4.5).
        "explanation": {
            "deciding_layer": ens.method,
            "layer_scores": ens.layers,
            "ml_probability": round(ml_prob, 4) if ml_prob is not None else None,
            "provenance": {
                "c2pa_present": bool(signals.get("has_c2pa")),
                "c2pa_claims_ai": bool(signals.get("c2pa_is_ai")),
                "metadata_stripped": bool(signals.get("metadata_is_stripped")),
                "platform_reencoded": bool(signals.get("platform_reencoded")),
                "ai_tool": result.ai_tool,
                "edit_tool": result.edit_tool,
            },
            "visual_artifacts": list(getattr(ens, "gemini_artifacts", []) or []),
            "caveats": [c for c in (
                "video shorter than 2s — low reliability" if signals.get("too_short_for_analysis") else None,
                "re-encoded by a platform — original file metadata lost" if signals.get("platform_reencoded") else None,
            ) if c],
        },
        "_signals": signals,
    }


@app.post("/label")
async def label_sample(file: UploadFile = File(...), is_ai: bool = True):
    """
    Submit a labeled video to improve the ML model.
    is_ai=true for AI-generated, false for real footage.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(await file.read())

    try:
        result = await run_in_threadpool(extract_features, tmp_path)
        classifier = get_classifier()
        classifier.add_sample(result.feature_vector, label=is_ai, source=file.filename)
        return {"message": "Sample added to training set", "label": "AI" if is_ai else "Real"}
    finally:
        os.unlink(tmp_path)


@app.post("/detect-frame")
@limiter.limit("60/minute")
async def detect_frame(request: Request, file: UploadFile = File(...)):
    """
    Last-resort detection from a SINGLE screen-captured frame (MediaProjection
    fallback on mobile, used when no video URL/file can be obtained).

    Frame-only analysis is the weakest signal — no metadata, no temporal cues —
    so the verdict leans on Gemini Vision and is reported conservatively.
    """
    import base64
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty frame")
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Frame too large")

    try:
        from analyzer.gemini_analyzer import analyze_image_with_gemini
        img_b64 = base64.standard_b64encode(raw).decode()
        g = await run_in_threadpool(analyze_image_with_gemini, img_b64)
    except Exception:
        g = None

    if g is None:
        return {
            "is_ai_generated": False,
            "verdict": "unknown",
            "confidence": 0.0,
            "confidence_pct": "0.0%",
            "ai_tool_detected": None,
            "detection_method": "Frame analysis unavailable",
            "source": "frame",
        }

    return {
        "is_ai_generated": g.verdict == "ai_generated",
        "verdict": g.verdict,
        "confidence": round(g.ai_probability, 4),
        "confidence_pct": f"{g.ai_probability * 100:.1f}%",
        "ai_tool_detected": None,
        "detection_method": f"Single-frame Gemini Vision: {g.reason}",
        "artifacts": g.artifacts,
        "source": "frame",
    }


@app.post("/train")
def train_model():
    """Train the ML model on all collected labeled samples."""
    classifier = get_classifier()
    result = classifier.train()
    return result


PLATFORM_DOMAINS = [
    "tiktok.com", "instagram.com", "youtube.com", "youtu.be",
    "twitter.com", "x.com", "reddit.com", "v.redd.it",
    "facebook.com", "fb.watch", "t.me", "snapchat.com",
    "pinterest.com", "pin.it", "twitch.tv", "clips.twitch.tv",
    "vimeo.com", "dailymotion.com", "triller.co", "rumble.com",
    "odysee.com", "bitchute.com", "streamable.com", "medal.tv",
    "likee.video", "kwai.com",
]

def _is_platform_url(url: str) -> bool:
    return any(d in url for d in PLATFORM_DOMAINS)


def _download_with_ytdlp(url: str, tmp_path: str) -> bool:
    """Use yt-dlp to download video. Tries multiple format strategies."""
    import subprocess, shutil
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return False

    base_args = [ytdlp, "--no-playlist", "--output", tmp_path,
                 "--no-warnings", "--quiet",
                 "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                 "--add-header", "Referer:https://www.google.com/"]

    # Strategy 1: HLS/m3u8 — works for YouTube even when DASH is blocked
    formats = [
        "91",           # YouTube HLS 144p (always available, not blocked)
        "93",           # YouTube HLS 360p
        "best[ext=mp4][filesize<10M]",
        "best[filesize<10M]",
        "worst",        # absolute fallback
    ]

    for fmt in formats:
        try:
            result = subprocess.run(
                base_args + ["--format", fmt, url],
                timeout=30, capture_output=True,
            )
            if result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10000:
                return True
            # Remove partial file before next attempt
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            if os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except: pass
    return False


def _download_direct(url: str, tmp_path: str) -> bool:
    """Direct HTTP download with Range request — only first 10MB needed."""
    LIMIT = 10 * 1024 * 1024
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            "Range": f"bytes=0-{LIMIT-1}",
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read(LIMIT)
        if len(data) < 1000:
            return False
        with open(tmp_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def download_video_from_url(url: str, tmp_path: str):
    """
    Shared URL → file pipeline used by /detect-url and the Telegram bot.

    Returns (ok, aigc_flagged, aigc_info):
      ok           — a playable video file was written to tmp_path
      aigc_flagged — the platform ITSELF labels this video as AI-generated
                     (TikTok AIGC label / YouTube "Altered or synthetic content" /
                     Meta "AI info"). This is definitive: the label lives in the
                     platform's page JSON, so it survives transcoding even though
                     the file's own metadata does not.
      aigc_info    — human-readable description of the label found
    """
    is_tiktok = any(x in url for x in ["tiktok.com", "vm.tiktok", "douyin.com"])
    ok = False
    aigc_flagged = False
    aigc_info = ""

    # Strategy 0: platform AI-disclosure label (YouTube/Instagram/Facebook).
    if not is_tiktok:
        try:
            from analyzer.platform_flags import check_platform_ai_flag
            pf = check_platform_ai_flag(url)
            if pf.flagged:
                return False, True, f"{pf.platform.capitalize()}: {pf.info}"
        except Exception:
            pass

    # Strategy 1: TikTok-specific resolver (gets CDN URL + AIGC labels)
    if is_tiktok:
        try:
            from analyzer.tiktok_resolver import download_tiktok_video
            ok, aigc_flagged, aigc_info = download_tiktok_video(url, tmp_path)
            if aigc_flagged:
                return ok, True, aigc_info
        except Exception:
            pass

    # Strategy 2: yt-dlp
    if not ok and _is_platform_url(url):
        ok = _download_with_ytdlp(url, tmp_path)

    # Strategy 3: Direct HTTP
    if not ok:
        ok = _download_direct(url, tmp_path)

    # Strategy 4: yt-dlp as last resort
    if not ok:
        ok = _download_with_ytdlp(url, tmp_path)

    return ok, aigc_flagged, aigc_info


@app.post("/detect-url")
@limiter.limit("30/minute")
async def detect_url(request: Request, url: str = Body(..., embed=True), deep: bool = False):
    """
    Detect AI from any video URL: TikTok, YouTube, Instagram, Telegram, direct MP4, etc.
    Uses yt-dlp for platform URLs, direct HTTP for CDN links.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL")

    suffix = ".mp4"
    for ext in [".mp4", ".mov", ".mkv", ".webm", ".m4v"]:
        if ext in url.lower():
            suffix = ext
            break

    tmp_path = tempfile.mktemp(suffix=suffix)

    try:
        # Download (up to ~60s of network IO) off the event loop
        ok, aigc_from_page, aigc_info = await run_in_threadpool(download_video_from_url, url, tmp_path)

        # Platform label without a downloadable file — still definitive
        if aigc_from_page and not ok:
            return {
                "url": url,
                "is_ai_generated": True,
                "verdict": "ai_generated",
                "confidence": 0.96,
                "confidence_pct": "96.0%",
                "ai_tool_detected": "Platform AI label",
                "edit_tool_detected": None,
                "detection_method": f"Platform AI disclosure: {aigc_info}",
                "deep_analysis_ran": False,
            }

        if not ok:
            raise HTTPException(400, "Could not download video. Check the URL or try uploading the file directly.")

        # If TikTok itself labeled this as AIGC — that's definitive
        if aigc_from_page:
            return {
                "url": url,
                "is_ai_generated": True,
                "verdict": "ai_generated",
                "confidence": 0.97,
                "confidence_pct": "97.0%",
                "ai_tool_detected": "TikTok AIGC",
                "edit_tool_detected": None,
                "detection_method": f"TikTok AIGC label detected: {aigc_info}",
                "deep_analysis_ran": False,
            }

        force_deep = deep or _is_platform_url(url)
        payload = await run_in_threadpool(run_full_analysis, tmp_path, force_deep)
        payload.pop("_signals", None)
        payload["url"] = url
        payload["aigc_page_label"] = aigc_from_page
        return payload
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/detect-batch")
async def detect_batch(
    request: Request,
    urls: list[str] = Body(...),
    key=Depends(get_api_key),
):
    """
    Enterprise batch endpoint — analyze up to 1000 URLs at once.
    Returns results as they complete (streaming JSON array).

    Requires Business tier or higher.
    Rate: counts each URL as 1 request against your monthly quota.

    Example:
        POST /detect-batch
        X-Api-Key: your_key
        Content-Type: application/json

        ["https://tiktok.com/...", "https://instagram.com/...", ...]
    """
    from fastapi.responses import StreamingResponse
    import json as _json

    # Tier check
    tier_info = TIERS.get(key.tier if key else "free", TIERS["free"])
    batch_limit = tier_info.get("batch_limit", 1)
    if len(urls) > batch_limit:
        raise HTTPException(
            400,
            f"Batch limit for {key.tier if key else 'free'} tier is {batch_limit} URLs. "
            f"Upgrade at https://web-zeta-ecru-80.vercel.app/dashboard"
        )

    # Check quota
    if key and key.remaining < len(urls):
        raise HTTPException(
            429,
            f"Insufficient quota: {key.remaining} requests remaining, "
            f"batch needs {len(urls)}. Upgrade at https://web-zeta-ecru-80.vercel.app/dashboard"
        )

    # Record all requests upfront
    if key:
        for _ in urls:
            record_request_by_id(key.key_id)

    def _analyze_batch_url(url: str, i: int) -> dict:
        """Full per-URL work (download + analyze) — runs on the threadpool."""
        tmp_path = tempfile.mktemp(suffix=".mp4")
        result_dict = {"url": url, "index": i}
        try:
            ok = _download_with_ytdlp(url, tmp_path)
            if not ok:
                ok = _download_direct(url, tmp_path)
            if not ok:
                result_dict.update({"error": "Download failed", "verdict": "unknown"})
            else:
                result = extract_features(tmp_path)
                classifier = get_classifier()
                ml_prob, _ = classifier.predict(result.feature_vector)
                conf = result.confidence
                verdict = result.verdict
                method = result.method
                has_camera = bool(result.signals.get("camera_origin_detected"))
                if ml_prob and not has_camera and conf < 0.1 and ml_prob >= 0.88:
                    conf = min(0.75, ml_prob); verdict = "ai_generated"
                if conf < 0.5 and not has_camera:
                    try:
                        from analyzer.visual_detector import detect_visual_with_motion as detect_visual
                        vis = detect_visual(tmp_path)
                        if vis.verdict == "ai_generated" and vis.confidence >= 0.62:
                            conf = max(conf, vis.confidence * 0.80)
                            method = vis.method
                            if conf >= 0.5: verdict = "ai_generated"
                    except Exception:
                        pass
                result_dict.update({
                    "verdict": verdict,
                    "is_ai_generated": verdict == "ai_generated",
                    "confidence": round(conf, 4),
                    "confidence_pct": f"{conf*100:.1f}%",
                    "ai_tool_detected": result.ai_tool,
                    "edit_tool_detected": result.edit_tool,
                    "detection_method": method,
                })
        except Exception as e:
            result_dict.update({"error": str(e), "verdict": "unknown"})
        finally:
            if os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except: pass
        return result_dict

    async def stream_results():
        yield "[\n"
        for i, url in enumerate(urls):
            # Off the event loop — a 1000-URL batch must not freeze the API
            result_dict = await run_in_threadpool(_analyze_batch_url, url, i)
            sep = "," if i < len(urls) - 1 else ""
            yield f"  {_json.dumps(result_dict)}{sep}\n"

        yield "]\n"

    return StreamingResponse(stream_results(), media_type="application/json")


@app.get("/pricing")
def pricing():
    """Returns available tiers and pricing."""
    return {
        "tiers": {
            name: {
                "requests_per_month": info["requests_per_month"],
                "batch_limit": info.get("batch_limit", 1),
                "price_usd_per_month": info.get("price_usd", 0),
                "price_per_request_usd": round(info.get("price_usd", 0) / max(1, info["requests_per_month"]), 6),
            }
            for name, info in TIERS.items()
        },
        "register_url": "https://web-zeta-ecru-80.vercel.app/dashboard",
        "docs_url": "https://ai-video-detector-production-a305.up.railway.app/docs",
        "contact": "enterprise@verifai.app",
    }


@app.get("/model/importance")
def feature_importance():
    classifier = get_classifier()
    importance = classifier.feature_importance()
    if importance is None:
        return {"error": "Model not trained yet. POST /train first."}
    return {"feature_importance": importance}


@app.get("/model/stats")
def model_stats():
    """Returns training dataset stats and model status."""
    import json
    from pathlib import Path

    data_path = Path("data/training_samples.json")
    if not data_path.exists():
        return {"trained": False, "samples": 0, "ai_samples": 0, "real_samples": 0}

    with open(data_path) as f:
        samples = json.load(f)

    ai   = sum(1 for s in samples if s["label"] == 1)
    real = sum(1 for s in samples if s["label"] == 0)
    classifier = get_classifier()

    return {
        "trained": classifier.is_trained,
        "total_samples": len(samples),
        "ai_samples": ai,
        "real_samples": real,
        "ready_to_train": ai >= 10 and real >= 10,
        "feature_vector_length": len(samples[0]["features"]) if samples else 0,
    }


@app.post("/model/calibrate")
async def calibrate(
    file: UploadFile = File(...),
    is_ai: bool = True,
):
    """
    Submit a labeled video + get back all signal scores for calibration.
    Use this to tune detection thresholds against known-AI or known-real videos.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(await file.read(FAST_READ_BYTES))

    try:
        result = await run_in_threadpool(extract_features, tmp_path, True)
        return {
            "filename": file.filename,
            "ground_truth": "ai_generated" if is_ai else "real",
            "predicted_verdict": result.verdict,
            "predicted_confidence": round(result.confidence, 4),
            "correct": (result.verdict == "ai_generated") == is_ai,
            "detection_method": result.method,
            "all_signals": result.signals,
            "feature_vector_length": len(result.feature_vector),
        }
    finally:
        os.unlink(tmp_path)


# ─── API Key management ────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str

class UpgradeRequest(BaseModel):
    email: str
    tier: str  # "pro" or "ultra"


@app.post("/rotate-key", tags=["billing"])
@limiter.limit("10/hour")
def rotate(request: Request, x_api_key: Optional[str] = Header(None)):
    """
    Replace your API key's secret (e.g. after a leak). Same account, tier
    and usage — only the secret changes. The old key stops working
    immediately; the new key is returned once.
    """
    if not x_api_key:
        raise HTTPException(401, "Present the current key in X-Api-Key to rotate it")
    new_key = rotate_key(x_api_key)
    if not new_key:
        raise HTTPException(401, "Invalid or inactive API key")
    return {"api_key": new_key,
            "message": "Key rotated. Store the new key now — it is shown only once."}


@app.post("/register", tags=["billing"])
@limiter.limit("10/hour")
def register(request: Request, body: RegisterRequest):
    """
    Get a free API key (100 requests/month).
    If the email already has a key, returns existing key info instead.
    """
    existing = get_key_by_email(body.email)
    if existing:
        return {
            "message": "You already have a key. Check your records for the original key.",
            "tier": existing.tier,
            "requests_this_month": existing.requests_this_month,
            "monthly_limit": existing.monthly_limit,
            "remaining": existing.remaining,
        }

    raw_key = create_key(body.email, tier="free")
    return {
        "api_key": raw_key,
        "tier": "free",
        "monthly_limit": TIERS["free"]["requests_per_month"],
        "message": "Save this key — it won't be shown again.",
        "docs": "Include it as X-Api-Key header in every request.",
    }


@app.post("/upgrade", tags=["billing"])
def upgrade(body: UpgradeRequest):
    """Returns a Stripe Checkout URL to upgrade to pro/ultra."""
    if body.tier not in ("pro", "ultra"):
        raise HTTPException(400, "tier must be 'pro' or 'ultra'")
    url = create_checkout_session(body.email, body.tier)
    return {"checkout_url": url}


@app.post("/stripe/webhook", tags=["billing"])
async def stripe_webhook(request: Request):
    """Stripe sends payment events here."""
    return await handle_webhook(request)


@app.get("/me", tags=["billing"])
def me(key=Depends(get_api_key)):
    """Returns usage stats for the authenticated API key."""
    if not key:
        raise HTTPException(401, "API key required")
    return {
        "email": key.email,
        "tier": key.tier,
        "requests_this_month": key.requests_this_month,
        "monthly_limit": key.monthly_limit,
        "remaining": key.remaining,
        "requests_total": key.requests_total,
    }

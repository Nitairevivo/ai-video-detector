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

from analyzer import extract_features
from models.classifier import get_classifier
from api.database import init_db, create_key, lookup_key, record_request, get_key_by_email, TIERS
from api.billing import create_checkout_session, handle_webhook

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

app = FastAPI(
    title="AI Video Detector API",
    description="Detect AI-generated videos by reading file signatures — no frame decoding required.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
async def detect(
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
        result = extract_features(tmp_path, deep=deep)
        classifier = get_classifier()
        ml_prob, _ = classifier.predict(result.feature_vector)

        final_confidence = result.confidence
        verdict = result.verdict
        method = result.method

        # ML model: only use if it gives VERY HIGH confidence (≥ 0.85) AND metadata gave no signal.
        # The current model is trained on synthetic data and causes false positives on real phone videos.
        # Only trust ML when it's extremely confident AND there's no camera-origin metadata.
        has_camera_origin = bool(result.signals.get("camera_origin_detected"))
        if ml_prob is not None and not has_camera_origin and result.confidence < 0.1:
            if ml_prob >= 0.88:
                # ML is very confident → use it but cap at 75% (not as trustworthy as metadata)
                final_confidence = min(0.75, ml_prob)
                verdict = "ai_generated"
                method = f"ML classifier ({ml_prob:.0%}) — {result.method}"
            # Below 0.88 → ignore ML, trust metadata-only result

        # Visual frame analysis (ML model + rules, survives TikTok re-encoding)
        if final_confidence < 0.5 and not has_camera_origin:
            try:
                from analyzer.visual_detector import detect_visual_with_motion as detect_visual
                vis = detect_visual(tmp_path)
                # Add visual signals to result signals
                result.signals.update({f"vis_{k}": v for k, v in vis.signals.items()})
                if vis.verdict == "ai_generated" and vis.confidence >= 0.62:
                    final_confidence = max(final_confidence, vis.confidence * 0.80)
                    method = vis.method
                    if final_confidence >= 0.5:
                        verdict = "ai_generated"
                elif vis.verdict == "real" and vis.confidence >= 0.90:
                    final_confidence = min(final_confidence, 0.06)
                    method = vis.method
            except Exception:
                pass

        # Gemini Vision: visual analysis for all inconclusive cases
        if final_confidence < 0.50 and not has_camera_origin:
            try:
                import time as _time
                from analyzer.gemini_analyzer import analyze_with_gemini
                gemini = None
                for _attempt in range(3):
                    gemini = analyze_with_gemini(tmp_path)
                    if gemini is not None:
                        break
                    _time.sleep(3 * (_attempt + 1))
                if gemini and gemini.frames_analyzed >= 3:
                    if gemini.verdict in ("ai_generated", "ai_edited") and gemini.confidence >= 0.70:
                        final_confidence = max(final_confidence, gemini.confidence * 0.90)
                        verdict = gemini.verdict
                        method = f"Gemini Vision: {gemini.reason}"
                    elif gemini.verdict == "real" and gemini.confidence >= 0.80:
                        final_confidence = min(final_confidence, 0.08)
                        method = f"Gemini Vision: {gemini.reason or 'No AI artifacts detected'}"
            except Exception:
                pass

        return {
            "filename": file.filename,
            "is_ai_generated": verdict == "ai_generated",
            "verdict": verdict,
            "confidence": round(final_confidence, 4),
            "confidence_pct": f"{final_confidence * 100:.1f}%",
            "ai_tool_detected": result.ai_tool,
            "edit_tool_detected": result.edit_tool,
            "detection_method": method,
            "deep_analysis_ran": bool(result.signals.get("freq_analyzed") or result.signals.get("visual_analyzed")),
            "signals": result.signals,
        }
    finally:
        os.unlink(tmp_path)


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
        result = extract_features(tmp_path)
        classifier = get_classifier()
        classifier.add_sample(result.feature_vector, label=is_ai, source=file.filename)
        return {"message": "Sample added to training set", "label": "AI" if is_ai else "Real"}
    finally:
        os.unlink(tmp_path)


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
    """Download video via yt-dlp Python API. Works for YouTube, TikTok, Instagram, etc."""
    try:
        import yt_dlp
    except ImportError:
        return False

    # Prefer a pre-muxed mp4 at low resolution (no ffmpeg required for merging).
    # Falls back to any available format if none match the quality constraints.
    fmt = (
        "best[ext=mp4][height<=480]"
        "/best[ext=mp4]"
        "/best[height<=480]"
        "/worst[ext=mp4]"
        "/worst"
    )

    ydl_opts = {
        "outtmpl": tmp_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 1,
        "format": fmt,
        # When ffmpeg is available (production), merge into mp4.
        "merge_output_format": "mp4",
        "nopart": True,
        "max_filesize": 200 * 1024 * 1024,  # skip formats >200 MB
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "Referer": "https://www.google.com/",
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10000
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
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


@app.post("/detect-url")
async def detect_url(url: str = Body(..., embed=True), deep: bool = False):
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

    is_tiktok = any(x in url for x in ["tiktok.com", "vm.tiktok", "douyin.com"])
    aigc_from_page = False
    aigc_info = ""

    try:
        ok = False

        # Strategy 1: TikTok-specific resolver (gets CDN URL + AIGC labels)
        if is_tiktok:
            try:
                from analyzer.tiktok_resolver import download_tiktok_video
                ok, aigc_from_page, aigc_info = download_tiktok_video(url, tmp_path)
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
        result = extract_features(tmp_path, deep=force_deep)
        classifier = get_classifier()
        ml_prob, _ = classifier.predict(result.feature_vector)

        final_confidence = result.confidence
        verdict = result.verdict
        method = result.method
        has_camera_origin = bool(result.signals.get("camera_origin_detected"))

        # Visual AI detection (ML model + rule-based, works after TikTok re-encoding)
        if final_confidence < 0.5 and not has_camera_origin:
            try:
                from analyzer.visual_detector import detect_visual_with_motion as detect_visual
                vis = detect_visual(tmp_path)
                if vis.verdict == "ai_generated" and vis.confidence >= 0.62:
                    final_confidence = max(final_confidence, vis.confidence * 0.80)
                    method = vis.method
                    if final_confidence >= 0.5:
                        verdict = "ai_generated"
                elif vis.verdict == "real" and vis.confidence >= 0.90:
                    # Strong visual evidence of real camera
                    final_confidence = min(final_confidence, 0.06)
                    method = vis.method
            except Exception:
                pass

        # Audio AI analysis
        if final_confidence < 0.5 and not has_camera_origin:
            try:
                from analyzer.audio_analyzer_ai import analyze_audio_ai
                audio_ai = analyze_audio_ai(tmp_path)
                if audio_ai.verdict == "ai_audio" and audio_ai.confidence >= 0.65:
                    final_confidence = max(final_confidence, audio_ai.confidence * 0.55)
                    method = f"Audio: {audio_ai.reason}"
                    if final_confidence >= 0.5:
                        verdict = "ai_generated"
            except Exception:
                pass

        # ML: only if very high confidence AND no camera origin
        if ml_prob is not None and not has_camera_origin and result.confidence < 0.1:
            if ml_prob >= 0.88:
                final_confidence = min(0.75, ml_prob)
                verdict = "ai_generated"
                method = f"ML classifier ({ml_prob:.0%})"

        # Gemini Vision: 0.70 threshold for all platforms
        if final_confidence < 0.50 and not has_camera_origin:
            try:
                import time as _time2
                from analyzer.gemini_analyzer import analyze_with_gemini
                gemini = None
                for _att in range(3):
                    gemini = analyze_with_gemini(tmp_path)
                    if gemini is not None: break
                    _time2.sleep(3 * (_att + 1))
                if gemini and gemini.frames_analyzed >= 3:
                    if gemini.verdict in ("ai_generated", "ai_edited") and gemini.confidence >= 0.70:
                        final_confidence = max(final_confidence, gemini.confidence * 0.90)
                        verdict = gemini.verdict
                        method = f"Gemini Vision: {gemini.reason}"
                    elif gemini.verdict == "real" and gemini.confidence >= 0.80:
                        # Gemini confidently says real → lower our score
                        final_confidence = min(final_confidence, 0.08)
                        method = f"Gemini Vision: {gemini.reason}"
            except Exception:
                pass

        return {
            "url": url,
            "is_ai_generated": verdict == "ai_generated",
            "verdict": verdict,
            "confidence": round(final_confidence, 4),
            "confidence_pct": f"{final_confidence * 100:.1f}%",
            "ai_tool_detected": result.ai_tool,
            "edit_tool_detected": result.edit_tool,
            "detection_method": method,
            "deep_analysis_ran": bool(result.signals.get("freq_analyzed") or result.signals.get("visual_analyzed")),
            "aigc_page_label": aigc_from_page,
        }
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
    import asyncio, json as _json

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
            record_request(key.key_id)

    async def stream_results():
        yield "[\n"
        for i, url in enumerate(urls):
            suffix = ".mp4"
            tmp_path = tempfile.mktemp(suffix=suffix)
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

            sep = "," if i < len(urls) - 1 else ""
            yield f"  {_json.dumps(result_dict)}{sep}\n"
            await asyncio.sleep(0)  # yield control

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
        result = extract_features(tmp_path, deep=True)
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


@app.post("/register", tags=["billing"])
def register(body: RegisterRequest):
    """
    Get a free API key (50 requests/month).
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

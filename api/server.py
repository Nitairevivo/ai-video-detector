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

        # Blend ML score when model is trained
        if ml_prob is not None:
            final_confidence = result.confidence * 0.4 + ml_prob * 0.6
            verdict = "ai_generated" if final_confidence >= 0.5 else "real"

        # Local deep analysis already ran inside extract_features if needed.
        # Only fall back to Gemini if deep analysis wasn't enough and confidence is ambiguous.
        if final_confidence < 0.5 and not deep and not result.signals.get("freq_analyzed"):
            try:
                from analyzer.gemini_analyzer import analyze_with_gemini
                gemini = analyze_with_gemini(tmp_path)
                if gemini and gemini.frames_analyzed >= 3:
                    if gemini.verdict in ("ai_generated", "ai_edited") and gemini.confidence >= 0.75:
                        final_confidence = gemini.confidence
                        verdict = gemini.verdict
                        method = f"Gemini Vision: {gemini.reason}"
                    elif gemini.verdict in ("ai_generated", "ai_edited"):
                        # Gemini suspects AI but not confident enough to override — keep existing score
                        method = f"Gemini Vision (low confidence): {gemini.reason}"
                    else:
                        # Gemini says real — use its confidence but don't go below existing score
                        final_confidence = max(final_confidence, 0.04)
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
    """Use yt-dlp to download first ~10MB of video from social platforms."""
    import subprocess, shutil
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return False
    try:
        result = subprocess.run(
            [
                ytdlp,
                "--no-playlist",
                "--format", "mp4/best[ext=mp4]/best",
                "--max-filesize", "10m",
                "--output", tmp_path,
                "--no-warnings",
                "--quiet",
                url,
            ],
            timeout=30,
            capture_output=True,
        )
        return result.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1000
    except Exception:
        return False


def _download_direct(url: str, tmp_path: str) -> bool:
    """Direct HTTP download for plain video URLs (cdn links, .mp4, etc.)."""
    DOWNLOAD_LIMIT = 10 * 1024 * 1024
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read(DOWNLOAD_LIMIT)
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

    try:
        ok = False
        if _is_platform_url(url):
            ok = _download_with_ytdlp(url, tmp_path)
        if not ok:
            ok = _download_direct(url, tmp_path)
        if not ok:
            # Last resort: try yt-dlp even if not a known platform
            ok = _download_with_ytdlp(url, tmp_path)
        if not ok:
            raise HTTPException(400, "Could not download video. Check the URL or try uploading the file directly.")

        # For URL submissions, always run deep analysis — platform CDN files
        # don't embed platform metadata tags, so platform_reencoded is never
        # set and the rule-based system falls through to 4% without deep analysis.
        force_deep = deep or _is_platform_url(url)
        result = extract_features(tmp_path, deep=force_deep)
        classifier = get_classifier()
        ml_prob, _ = classifier.predict(result.feature_vector)

        final_confidence = result.confidence
        verdict = result.verdict
        method = result.method

        if ml_prob is not None:
            final_confidence = result.confidence * 0.4 + ml_prob * 0.6
            verdict = "ai_generated" if final_confidence >= 0.5 else "real"

        if final_confidence < 0.5 and not force_deep and not result.signals.get("freq_analyzed"):
            try:
                from analyzer.gemini_analyzer import analyze_with_gemini
                gemini = analyze_with_gemini(tmp_path)
                if gemini and gemini.frames_analyzed >= 3:
                    if gemini.verdict in ("ai_generated", "ai_edited") and gemini.confidence >= 0.75:
                        final_confidence = gemini.confidence
                        verdict = gemini.verdict
                        method = f"Gemini Vision: {gemini.reason}"
                    elif gemini.verdict in ("ai_generated", "ai_edited"):
                        method = f"Gemini Vision (low confidence): {gemini.reason}"
                    else:
                        final_confidence = max(final_confidence, 0.04)
                        method = f"Gemini Vision: {gemini.reason or 'No AI artifacts detected'}"
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
        }
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


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

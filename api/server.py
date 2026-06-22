"""
FastAPI server — upload a video, get AI detection results in seconds.
"""
import os
import tempfile
import urllib.request
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from analyzer import extract_features
from models.classifier import get_classifier

app = FastAPI(
    title="AI Video Detector",
    description="Detects AI-generated videos by reading file signatures — no frame decoding required.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
async def detect(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format: {suffix}. Use: {SUPPORTED_FORMATS}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        # Read first 10MB — enough for all metadata + container signals.
        # ffprobe for codec analysis reads the file separately on disk.
        chunk = await file.read(FAST_READ_BYTES)
        if not chunk:
            raise HTTPException(400, "Empty file")
        tmp.write(chunk)
        # Do NOT drain remaining bytes — for large files (100MB+) this can hit Railway's
        # 30s request timeout. The connection closes cleanly without draining.

    try:
        result = extract_features(tmp_path)
        classifier = get_classifier()
        ml_prob, ml_is_ai = classifier.predict(result.feature_vector)

        # Blend rule-based + ML if available
        if ml_prob is not None:
            final_confidence = result.confidence * 0.4 + ml_prob * 0.6
            method = f"ML+Rules ({result.method})"
        else:
            final_confidence = result.confidence
            method = result.method + " (rules only — train model for higher accuracy)"

        return {
            "filename": file.filename,
            "is_ai_generated": final_confidence >= 0.5,
            "confidence": round(final_confidence, 4),
            "confidence_pct": f"{final_confidence * 100:.1f}%",
            "ai_tool_detected": result.ai_tool,
            "detection_method": method,
            "signals": result.signals,
            "rule_based_confidence": round(result.confidence, 4),
            "ml_confidence": round(ml_prob, 4) if ml_prob is not None else None,
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
async def detect_url(url: str = Body(..., embed=True)):
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

        result = extract_features(tmp_path)
        classifier = get_classifier()
        ml_prob, _ = classifier.predict(result.feature_vector)

        if ml_prob is not None:
            final_confidence = result.confidence * 0.4 + ml_prob * 0.6
            method = f"ML+Rules ({result.method})"
        else:
            final_confidence = result.confidence
            method = result.method

        return {
            "url": url,
            "is_ai_generated": final_confidence >= 0.5,
            "confidence": round(final_confidence, 4),
            "confidence_pct": f"{final_confidence * 100:.1f}%",
            "ai_tool_detected": result.ai_tool,
            "detection_method": method,
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

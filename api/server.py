"""
FastAPI server — upload a video, get AI detection results in seconds.
"""
import os
import json
import re
import tempfile
import time
import urllib.parse
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

    # Account endpoints don't consume quota — checking your usage isn't usage
    if request.url.path not in ("/me", "/rotate-key"):
        record_request(x_api_key)
    return key


def get_optional_api_key(request: Request, x_api_key: Optional[str] = Header(None)):
    """
    Key-optional auth for the core detect endpoints: anonymous callers stay
    allowed (public demo path, IP rate-limited), but when a key IS presented
    it must be valid, quota is enforced and usage is recorded — so paid API
    traffic is actually billed and lands in the customer's audit trail.
    """
    if not x_api_key:
        return None
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
IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp',
                 '.tif', '.tiff', '.heic', '.heif', '.avif'}
# Upload cap: enough for any social-video file, small enough not to fill the
# container's disk. Deep analysis (Gemini frame pairs, visual, audio) needs the
# WHOLE file — MP4s often keep the moov index at the end, so a truncated file
# can lose all frames, not just the tail.
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500MB


async def _save_upload(file: UploadFile, tmp, limit: int = MAX_UPLOAD_BYTES) -> int:
    """Stream an upload to disk in chunks (bounded memory). Returns bytes written."""
    total = 0
    while True:
        chunk = await file.read(1 << 20)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(400, f"File too large (max {limit // (1024*1024)}MB)")
        tmp.write(chunk)
    return total


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
    mode: str = "full",
    key=Depends(get_optional_api_key),
):
    """
    Analyze a video file for AI generation.
    mode=fast: code-first path (~1s) — metadata/C2PA/container/codec only, no
      frame decoding. Definitive on hard evidence; best when the original file
      is available (its metadata is intact).
    deep=true: also runs visual + frequency analysis (~10s extra, better for
      re-encoded/stripped videos with no code evidence).
    """
    suffix = Path(file.filename).suffix.lower()
    is_image = suffix in IMAGE_FORMATS
    if suffix not in SUPPORTED_FORMATS and not is_image:
        raise HTTPException(400, f"Unsupported format: {suffix}. Use video {sorted(SUPPORTED_FORMATS)} or image {sorted(IMAGE_FORMATS)}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
        try:
            written = await _save_upload(file, tmp)
        except BaseException:
            # Any failure (client disconnect, OSError, cancellation) — not just
            # HTTPException — must not leave the temp file on disk.
            os.unlink(tmp_path)
            raise
        if written == 0:
            os.unlink(tmp_path)
            raise HTTPException(400, "Empty file")

    try:
        # Analysis takes 10-60s of CPU/IO — run it off the event loop so one
        # video doesn't freeze every other request on the server.
        if is_image:
            payload = await run_in_threadpool(run_image_analysis, tmp_path)
        elif mode == "fast":
            payload = await run_in_threadpool(run_fast_analysis, tmp_path)
        else:
            payload = await run_in_threadpool(run_full_analysis, tmp_path, deep)
        payload["filename"] = file.filename
        payload["signals"] = payload.pop("_signals", {})
        if key:
            from api.database import log_detection
            log_detection(key.key_id, payload["verdict"], payload["confidence"],
                          source=file.filename or "upload")
        return payload
    finally:
        os.unlink(tmp_path)


def run_fast_analysis(tmp_path: str, platform_flag: dict = None) -> dict:
    """
    FAST code-first path (~1s): read only the "code" layers — file metadata,
    C2PA credentials, container structure, codec fingerprints — plus any
    platform AI-disclosure label passed in. Never decodes frames, never calls
    Gemini. Definitive when hard evidence exists (C2PA / AI-tool tag / signed
    platform label); otherwise reports low confidence quickly instead of
    spending seconds on visual analysis.

    This is the accurate, near-instant path when the original file is
    available (Telegram, WhatsApp-as-document, direct upload) — the metadata
    is intact so "reading the code behind the video" is enough.
    """
    result = extract_features(tmp_path, code_only=True)
    signals = result.signals or {}

    verdict = result.verdict
    confidence = result.confidence
    method = result.method
    ai_tool = result.ai_tool

    # A platform's own AI label (TikTok AIGC / YouTube / Meta) is definitive
    # and survives re-encoding — fold it in as top-tier evidence.
    if platform_flag and platform_flag.get("flagged"):
        verdict, confidence = "ai_generated", 0.96
        method = f"Platform AI disclosure: {platform_flag.get('info', '')}"
        ai_tool = ai_tool or "Platform AI label"

    return {
        "is_ai_generated": verdict == "ai_generated",
        "verdict": verdict,
        "confidence": round(confidence, 4),
        "confidence_pct": f"{confidence * 100:.1f}%",
        "ai_tool_detected": ai_tool,
        "edit_tool_detected": result.edit_tool,
        "detection_method": method,
        "deep_analysis_ran": False,
        "mode": "fast",
        "explanation": {
            "deciding_layer": method,
            "provenance": {
                "c2pa_present": bool(signals.get("has_c2pa")),
                "c2pa_claims_ai": bool(signals.get("c2pa_is_ai")),
                "synthetic_media_marker": bool(signals.get("synthetic_media_marker")),
                "iptc_digital_source_type": signals.get("iptc_digital_source_type"),
                "camera_provenance": bool(signals.get("capture_origin_marker")),
                "metadata_stripped": bool(signals.get("metadata_is_stripped")),
                "platform_reencoded": bool(signals.get("platform_reencoded")),
                "platform_ai_label": bool(platform_flag and platform_flag.get("flagged")),
                "ai_tool": ai_tool,
                "edit_tool": result.edit_tool,
            },
            "caveats": [c for c in (
                "no hard code evidence found — for stripped/re-encoded video, run full analysis for a visual check"
                if (confidence < 0.5 and (signals.get("metadata_is_stripped") or signals.get("platform_reencoded")))
                else None,
            ) if c],
        },
        "_signals": signals,
    }


def run_image_analysis(tmp_path: str) -> dict:
    """
    Code-first still-image analysis — the image counterpart of the fast video
    path. Reads EXIF / C2PA / IPTC / PNG-metadata / tool tags; near-instant and
    never decodes pixels for a verdict when provenance exists.
    """
    from analyzer.image_analyzer import analyze_image
    r = analyze_image(tmp_path)
    s = r.signals or {}
    return {
        "is_ai_generated": r.verdict == "ai_generated",
        "verdict": r.verdict,
        "confidence": round(r.confidence, 4),
        "confidence_pct": f"{r.confidence * 100:.1f}%",
        "ai_tool_detected": r.ai_tool,
        "edit_tool_detected": None,
        "detection_method": r.method,
        "media_type": "image",
        "mode": "fast",
        "deep_analysis_ran": False,
        "explanation": {
            "deciding_layer": r.method,
            "provenance": {
                "c2pa_present": bool(s.get("has_c2pa")),
                "c2pa_claims_ai": bool(s.get("c2pa_is_ai")),
                "synthetic_media_marker": bool(s.get("synthetic_media_marker")),
                "iptc_digital_source_type": s.get("iptc_digital_source_type"),
                "camera_provenance": bool(s.get("camera_provenance")),
                "metadata_stripped": bool(s.get("metadata_is_stripped")),
                "ai_tool": r.ai_tool,
            },
            "caveats": [c for c in (
                "image has no metadata (screenshot / re-saved / platform-stripped) — no provenance to read"
                if s.get("metadata_is_stripped") else None,
            ) if c],
        },
        "_signals": s,
    }


def run_full_analysis(tmp_path: str, deep: bool = True) -> dict:
    """
    Shared analysis pipeline: metadata/container features → Gemini-base ensemble
    (Gemini + visual + audio + frame-ML fused). Used by /detect, /detect-url
    and the Telegram bot.
    """
    from analyzer.ensemble import analyze_ensemble, _run_gemini
    from concurrent.futures import ThreadPoolExecutor

    # A verdict must rest on decoded frames. An undecodable file (HTML saved
    # as .mp4, truncated download, wrong format) would otherwise flow through
    # feature extraction as an all-defaults vector and the classifier would
    # return a constant, confidently wrong score.
    try:
        import imageio_ffmpeg
        _gen = imageio_ffmpeg.read_frames(tmp_path)
        next(_gen)  # metadata
        next(_gen)  # first decoded frame
        _gen.close()
    except StopIteration:
        raise HTTPException(422, "File is not a decodable video — try uploading the original file.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "File is not a decodable video — try uploading the original file.")

    # Overlap the Gemini vision call (the slowest layer) with local feature
    # extraction so the total is ~max(gemini, features) instead of their sum —
    # this is what keeps the full path inside the ~5s response target.
    with ThreadPoolExecutor(max_workers=1) as ex:
        gfut = ex.submit(_run_gemini, tmp_path)
        result = extract_features(tmp_path, deep=deep)
        classifier = get_classifier()
        ml_prob, _ = classifier.predict(result.feature_vector)
        try:
            gemini = gfut.result()
        except Exception:
            gemini = None

    ens = analyze_ensemble(tmp_path, result, ml_prob, use_gemini=True, gemini_result=gemini)

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
                "synthetic_media_marker": bool(signals.get("synthetic_media_marker")),
                "iptc_digital_source_type": signals.get("iptc_digital_source_type"),
                "camera_provenance": bool(signals.get("capture_origin_marker")),
                "metadata_stripped": bool(signals.get("metadata_is_stripped")),
                "platform_reencoded": bool(signals.get("platform_reencoded")),
                "ai_tool": result.ai_tool,
                "edit_tool": result.edit_tool,
            },
            "visual_artifacts": list(getattr(ens, "gemini_artifacts", []) or []),
            # Per-frame suspicion (0=natural … 1=AI-like) when the visual layer
            # ran — drives the timeline in the web forensics report.
            "frame_timeline": list(signals.get("visual_frame_timeline", []) or []),
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
        try:
            await _save_upload(file, tmp)
        except BaseException:
            os.unlink(tmp_path)
            raise

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


@app.post("/detect-frames")
@limiter.limit("30/minute")
async def detect_frames(request: Request, files: list[UploadFile] = File(...)):
    """
    Detection from an ordered BURST of screen frames (~0.6s apart), captured by
    the mobile MediaProjection path. Temporal comparison across the burst is a
    far stronger signal than the single-frame /detect-frame fallback.
    """
    import base64
    frames = []
    for f in files[:8]:
        raw = await f.read()
        if not raw:
            continue
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(400, "Frame too large")
        frames.append(base64.standard_b64encode(raw).decode())
    if not frames:
        raise HTTPException(400, "No frames")

    try:
        from analyzer.gemini_analyzer import analyze_frame_burst_with_gemini
        g = await run_in_threadpool(analyze_frame_burst_with_gemini, frames)
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
            "source": "frames",
            "frames_analyzed": len(frames),
        }

    return {
        "is_ai_generated": g.verdict == "ai_generated",
        "verdict": g.verdict,
        "confidence": round(g.ai_probability, 4),
        "confidence_pct": f"{g.ai_probability * 100:.1f}%",
        "ai_tool_detected": None,
        "detection_method": f"Screen burst ({len(frames)} frames), Gemini temporal: {g.reason}",
        "artifacts": g.artifacts,
        "source": "frames",
        "frames_analyzed": len(frames),
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

def _host_of(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _host_matches(host: str, domains) -> bool:
    """True if host IS one of the domains or a subdomain of it — matched on the
    parsed hostname, never a substring of the whole URL (so a credentials trick
    like `http://tiktok.com@169.254.169.254/` does not count as a platform URL)."""
    return any(host == d or host.endswith("." + d) for d in domains)


def _is_platform_url(url: str) -> bool:
    return _host_matches(_host_of(url), PLATFORM_DOMAINS)


# Rotating User-Agents — a fixed UA is an easy block target for CDNs (roadmap 2.3)
_DOWNLOAD_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def _pick_ua() -> str:
    import random
    return random.choice(_DOWNLOAD_UAS)


_YT_INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
_YT_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/|v/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_YT_PLAYER_CLIENTS = [
    ({"client": {"clientName": "ANDROID", "clientVersion": "19.44.38",
                 "androidSdkVersion": 34, "hl": "en", "osName": "Android", "osVersion": "14"}},
     "com.google.android.youtube/19.44.38 (Linux; U; Android 14) gzip"),
    ({"client": {"clientName": "IOS", "clientVersion": "19.45.4",
                 "deviceModel": "iPhone16,2", "hl": "en", "osName": "iOS", "osVersion": "18.1.0.22B83"}},
     "com.google.ios.youtube/19.45.4 (iPhone16,2; U; CPU iOS 18_1_0 like Mac OS X)"),
    ({"client": {"clientName": "TVHTML5_SIMPLY_EMBEDDED_PLAYER", "clientVersion": "2.0", "hl": "en"},
      "thirdParty": {"embedUrl": "https://www.youtube.com"}}, _DOWNLOAD_UAS[0]),
]


def _download_youtube_innertube(url: str, tmp_path: str) -> bool:
    """
    Fetch a YouTube video via the innertube 'player' API with a mobile/embedded
    client. Those clients return progressive (muxed audio+video) stream URLs
    that download directly — no signature-cipher deciphering. This often works
    where yt-dlp's default web client hits YouTube's bot wall. Same 60MB cap and
    magic-byte guard as the other strategies.
    """
    m = _YT_ID_RE.search(url)
    if not m:
        return False
    vid = m.group(1)
    for context, ua in _YT_PLAYER_CLIENTS:
        try:
            body = json.dumps({
                "context": context, "videoId": vid,
                "contentCheckOk": True, "racyCheckOk": True,
            }).encode()
            req = urllib.request.Request(
                f"https://www.youtube.com/youtubei/v1/player?key={_YT_INNERTUBE_KEY}&prettyPrint=false",
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": ua,
                         "Accept-Language": "en-US,en;q=0.9"},
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read(4 * 1024 * 1024).decode("utf-8", errors="ignore"))
        except Exception:
            continue
        formats = [f for f in (data.get("streamingData", {}).get("formats") or [])
                   if f.get("url") and "mp4" in (f.get("mimeType") or "")]
        if not formats:
            continue
        muxed = [f for f in formats if "audio" in (f.get("mimeType") or "")]
        pool = muxed or formats
        chosen = next((f for f in pool if f.get("itag") == 18), pool[0])
        if _download_direct(chosen["url"], tmp_path):
            return True
    return False


# Public YouTube mirror instances that PROXY the video bytes through their own
# domain: Piped (`videoStreams[].url` on the instance's proxy host) and
# Invidious (`/latest_version?...&local=true`). YouTube's bot-wall blocks
# googlevideo.com from datacenter IPs — these instances fetch upstream
# themselves and re-serve the bytes, so the download succeeds where every
# direct strategy fails. Instance lists rot over time, so allow overriding
# without a deploy via VIDEO_MIRROR_INSTANCES="piped:host1,invidious:host2".
_PIPED_APIS = [
    "pipedapi.kavin.rocks",
    "pipedapi.adminforge.de",
    "api.piped.private.coffee",
]
_INVIDIOUS_HOSTS = [
    "inv.nadeko.net",
    "yewtu.be",
    "invidious.nerdvpn.de",
    "iv.ggtyler.dev",
]


def _mirror_instances():
    env = os.environ.get("VIDEO_MIRROR_INSTANCES", "").strip()
    if env:
        piped, inv = [], []
        for tok in env.split(","):
            kind, _, host = tok.strip().partition(":")
            if kind == "piped" and host:
                piped.append(host)
            elif kind == "invidious" and host:
                inv.append(host)
        return piped, inv

    # Live discovery: both projects publish machine-readable lists of the
    # instances that are currently up. A hardcoded list rots in weeks (YouTube
    # actively hunts these mirrors); the live list is self-healing. Hardcoded
    # hosts remain only as a fallback when discovery itself is unreachable.
    piped, inv = [], []
    try:
        req = urllib.request.Request(
            "https://api.invidious.io/instances.json?sort_by=health",
            headers={"User-Agent": _pick_ua()})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read(1024 * 1024).decode("utf-8", errors="ignore"))
        for _name, meta in data:
            if not isinstance(meta, dict) or meta.get("type") != "https":
                continue
            if meta.get("api") is False:
                continue
            host = (meta.get("uri") or "").replace("https://", "").strip("/")
            if host:
                inv.append(host)
            if len(inv) >= 8:
                break
    except Exception as e:
        print(f"[mirror] invidious discovery failed: {e!r}")
    try:
        req = urllib.request.Request(
            "https://piped-instances.kavin.rocks/",
            headers={"User-Agent": _pick_ua()})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read(1024 * 1024).decode("utf-8", errors="ignore"))
        for m in data:
            host = (m.get("api_url") or "").replace("https://", "").strip("/")
            if host:
                piped.append(host)
            if len(piped) >= 6:
                break
    except Exception as e:
        print(f"[mirror] piped discovery failed: {e!r}")

    piped += [h for h in _PIPED_APIS if h not in piped]
    inv += [h for h in _INVIDIOUS_HOSTS if h not in inv]
    print(f"[mirror] candidates: {len(piped)} piped, {len(inv)} invidious")
    return piped[:8], inv[:10]


def _download_youtube_via_mirror(url: str, tmp_path: str) -> bool:
    """Download a YouTube video through a Piped/Invidious mirror proxy."""
    m = _YT_ID_RE.search(url)
    if not m:
        return False
    vid = m.group(1)
    piped, invidious = _mirror_instances()

    def _accept() -> bool:
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10000 \
                and _looks_like_video(tmp_path):
            return True
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return False

    deadline = time.time() + 75   # total budget — dead instances must not eat the request

    for host in piped:
        if time.time() > deadline:
            break
        try:
            req = urllib.request.Request(
                f"https://{host}/streams/{vid}",
                headers={"User-Agent": _pick_ua()})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read(2 * 1024 * 1024).decode("utf-8", errors="ignore"))
            streams = [s for s in (data.get("videoStreams") or [])
                       if s.get("url") and not s.get("videoOnly")
                       and "mp4" in (s.get("mimeType") or "")]
            if not streams:
                print(f"[mirror] piped {host}: no muxed mp4 streams")
            for s in streams[:2]:
                if _download_direct(s["url"], tmp_path) and _accept():
                    print(f"[mirror] SUCCESS via piped {host}")
                    return True
        except Exception as e:
            print(f"[mirror] piped {host}: {e!r}")
            continue

    for host in invidious:
        if time.time() > deadline:
            break
        for itag in ("18", "22"):   # muxed 360p / 720p mp4
            try:
                u = f"https://{host}/latest_version?id={vid}&itag={itag}&local=true"
                if _download_direct(u, tmp_path) and _accept():
                    print(f"[mirror] SUCCESS via invidious {host} itag={itag}")
                    return True
            except Exception as e:
                print(f"[mirror] invidious {host} itag={itag}: {e!r}")
                continue
    return False


def _download_via_cobalt(url: str, tmp_path: str) -> bool:
    """Download ANY supported URL through a cobalt instance (the modern,
    actively-maintained successor to youtube-dl-as-a-service). Cobalt fetches
    the media upstream itself and 'tunnels' the bytes back through its own
    domain, so it works from a datacenter IP that YouTube/TikTok would refuse.
    Instances are overridable via COBALT_INSTANCES="host1,host2" (a self-hosted
    instance with an API key is the bulletproof option — set COBALT_API_KEY)."""
    env = os.environ.get("COBALT_INSTANCES", "").strip()
    hosts = [h.strip() for h in env.split(",") if h.strip()] or [
        "cobalt-api.kwiatekmiki.com",
        "capi.oei.moe",
        "co.otomir23.me",
    ]
    api_key = os.environ.get("COBALT_API_KEY", "").strip()
    body = json.dumps({"url": url, "videoQuality": "360",
                       "filenameStyle": "basic"}).encode()
    for host in hosts:
        try:
            headers = {"Accept": "application/json",
                       "Content-Type": "application/json",
                       "User-Agent": _pick_ua()}
            if api_key:
                headers["Authorization"] = f"Api-Key {api_key}"
            req = urllib.request.Request(f"https://{host}/", data=body,
                                         headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read(512 * 1024).decode("utf-8", errors="ignore"))
            status = data.get("status")
            media = data.get("url")
            if status in ("tunnel", "redirect", "stream") and media:
                if _download_direct(media, tmp_path) and os.path.exists(tmp_path) \
                        and os.path.getsize(tmp_path) > 10000 and _looks_like_video(tmp_path):
                    print(f"[cobalt] SUCCESS via {host}")
                    return True
            else:
                print(f"[cobalt] {host}: status={status} err={data.get('error')}")
        except Exception as e:
            print(f"[cobalt] {host}: {e!r}")
            continue
    return False


def _download_with_ytdlp(url: str, tmp_path: str) -> bool:
    """Use yt-dlp to download video. Tries multiple format strategies."""
    import subprocess, shutil
    ytdlp = shutil.which("yt-dlp")
    if not ytdlp:
        return False

    base_args = [ytdlp, "--no-playlist", "--output", tmp_path,
                 "--no-warnings", "--quiet",
                 "--user-agent", _pick_ua(),
                 # Ask yt-dlp to try the datacenter-friendlier player clients in
                 # order — the mobile/TV/embedded clients still return
                 # downloadable progressive URLs where the default web client
                 # hits YouTube's bot wall. This is the single biggest lever on
                 # YouTube success rate from a server IP.
                 "--extractor-args",
                 "youtube:player_client=android,ios,tv_embedded,web_embedded,web_safari",
                 "--add-header", "Referer:https://www.google.com/"]

    # Strategy 1: HLS/m3u8 — works for YouTube even when DASH is blocked
    formats = [
        "18",           # progressive muxed 360p mp4 (single file, no mux needed)
        "91",           # YouTube HLS 144p (always available, not blocked)
        "93",           # YouTube HLS 360p
        "best[ext=mp4][filesize<20M]",
        "best[filesize<20M]",
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


def _is_safe_public_url(url: str) -> bool:
    """SSRF guard: only allow http(s) URLs whose host resolves entirely to
    public addresses. Blocks cloud metadata (169.254.169.254), loopback,
    private and link-local ranges so a user-supplied URL can't make the server
    fetch internal services."""
    import ipaddress
    import socket
    from urllib.parse import urlparse
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
        return True
    except Exception:
        return False


def _looks_like_video(path: str) -> bool:
    """Magic-byte sniff: does this file plausibly hold a media container?
    Guards the URL pipeline against a platform's HTML page saved as '.mp4'
    (what a blocked yt-dlp + direct-HTTP fallback produces) — feeding that to
    the feature extractor yields a degenerate vector and a bogus verdict."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except Exception:
        return False
    if len(head) < 12:
        return False
    if head[4:8] == b"ftyp":                            # MP4 / MOV / M4V
        return True
    if head[:4] == b"\x1aE\xdf\xa3":                    # WebM / MKV (EBML)
        return True
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":   # AVI
        return True
    if head[:4] == b"OggS" or head[:3] == b"FLV":       # Ogg / FLV
        return True
    if head.lstrip()[:1] in (b"<", b"{"):               # HTML / JSON error page
        return False
    # Unrecognized but binary (e.g. MPEG-TS): let the decoder decide downstream.
    return True


def _download_direct(url: str, tmp_path: str) -> bool:
    """
    Direct HTTP download, capped at 60MB. The cap matters: deep analysis
    needs the whole file, and social videos are almost always well under it.
    """
    if not _is_safe_public_url(url):
        return False
    LIMIT = 60 * 1024 * 1024
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _pick_ua(),
            "Range": f"bytes=0-{LIMIT-1}",
            "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype or "application/json" in ctype:
                return False  # a watch page / error page, not the video itself
            data = resp.read(LIMIT)
        if len(data) < 1000:
            return False
        with open(tmp_path, "wb") as f:
            f.write(data)
        if not _looks_like_video(tmp_path):
            os.unlink(tmp_path)
            return False
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
    # SSRF guard, UNCONDITIONAL: every strategy below (TikTok resolver,
    # platform-flags, yt-dlp, direct HTTP) issues a request derived from `url`,
    # so gate them all on a host that resolves only to public addresses. This
    # runs before the platform branch precisely so a credentials/spoof trick
    # (`http://tiktok.com@169.254.169.254/`) can't skip the check.
    if not _is_safe_public_url(url):
        return False, False, "blocked: URL is not a public address"

    is_tiktok = _host_matches(_host_of(url), ("tiktok.com", "douyin.com")) \
        or _host_of(url).startswith("vm.tiktok")
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

    # Strategy 1.5: YouTube via innertube (progressive mobile-client stream).
    # Tried before yt-dlp because YouTube bot-walls yt-dlp's web client from
    # datacenter IPs; the mobile-client player API often still works.
    if not ok and _host_matches(_host_of(url), ("youtube.com", "youtu.be")):
        ok = _download_youtube_innertube(url, tmp_path)

    # Strategy 2: yt-dlp
    if not ok and _is_platform_url(url):
        ok = _download_with_ytdlp(url, tmp_path)

    # Strategy 2.5: YouTube mirror proxies (Piped / Invidious `local=true`).
    # The bytes come from the mirror's own domain — works even when
    # googlevideo.com refuses the datacenter IP outright.
    if not ok and _host_matches(_host_of(url), ("youtube.com", "youtu.be")):
        ok = _download_youtube_via_mirror(url, tmp_path)

    # Strategy 2.7: cobalt tunnel — works for YouTube, TikTok, Instagram, X…
    # from a datacenter IP by proxying the bytes through the cobalt instance.
    if not ok and _is_platform_url(url):
        ok = _download_via_cobalt(url, tmp_path)

    # Strategy 3: Direct HTTP
    if not ok:
        ok = _download_direct(url, tmp_path)

    # Strategy 4: yt-dlp as last resort
    if not ok:
        ok = _download_with_ytdlp(url, tmp_path)

    # Whatever strategy claimed success must have produced an actual media
    # file — never hand an HTML/error page to the analyzers.
    if ok and not _looks_like_video(tmp_path):
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        ok = False

    return ok, aigc_flagged, aigc_info


@app.post("/detect-url")
@limiter.limit("30/minute")
async def detect_url(request: Request, url: str = Body(..., embed=True), deep: bool = False,
                     key=Depends(get_optional_api_key)):
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
            _yt = _host_matches(_host_of(url), ("youtube.com", "youtu.be"))
            raise HTTPException(400,
                "Couldn't fetch this video from the server"
                + (" — YouTube blocks server downloads especially hard. "
                   "Download it and drag the file in, or try a TikTok/Instagram link."
                   if _yt else
                   ". Try uploading the file directly, or share it to the app."))

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
        signals = payload.pop("_signals", {}) or {}

        # TikTok (and others) are rolling out C2PA on downloaded content —
        # log sightings so we know the moment the rollout reaches us (roadmap 5.2).
        if signals.get("has_c2pa") and _is_platform_url(url):
            print(_obs_json.dumps({
                "evt": "platform_c2pa_seen",
                "host": urllib.parse.urlparse(url).netloc,
                "c2pa_is_ai": bool(signals.get("c2pa_is_ai")),
            }))

        payload["url"] = url
        payload["aigc_page_label"] = aigc_from_page
        if key:
            from api.database import log_detection
            log_detection(key.key_id, payload["verdict"], payload["confidence"],
                          source=urllib.parse.urlparse(url).netloc or url[:60])
        return payload
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/detect-batch")
@limiter.limit("10/minute")
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
        try:
            await _save_upload(file, tmp)
        except BaseException:
            os.unlink(tmp_path)
            raise

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


class FeedbackRequest(BaseModel):
    verdict: str                      # the verdict VerifAI gave
    confidence: float
    user_says_ai: bool                # the user's ground truth
    method: str = ""
    source: str = "web"
    signals: Optional[dict] = None    # numeric signals only — never media


@app.post("/feedback")
@limiter.limit("20/hour")
def submit_feedback(request: Request, body: FeedbackRequest):
    """
    Report whether a verdict was right (the learning-loop's raw material).
    Stores verdict metadata + numeric signals only — never the video itself.
    """
    from api.database import add_feedback
    import json as _json
    if body.verdict not in ("ai_generated", "ai_edited", "real", "unknown"):
        raise HTTPException(400, "Invalid verdict")
    total = add_feedback(
        verdict=body.verdict,
        confidence=max(0.0, min(1.0, body.confidence)),
        user_says_ai=body.user_says_ai,
        method=body.method,
        source=body.source,
        signals_json=_json.dumps(body.signals or {}),
    )
    return {"message": "Thanks — feedback recorded", "total_feedback": total}


@app.get("/feedback/stats")
def get_feedback_stats():
    """Live agreement stats between users and the model."""
    from api.database import feedback_stats
    return feedback_stats()


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
    """Returns usage stats for the authenticated API key, incl. 30-day history."""
    if not key:
        raise HTTPException(401, "API key required")
    from api.database import usage_history, recent_detections
    return {
        "email": key.email,
        "tier": key.tier,
        "requests_this_month": key.requests_this_month,
        "monthly_limit": key.monthly_limit,
        "remaining": key.remaining,
        "requests_total": key.requests_total,
        "usage_history": usage_history(key.key_id, days=30),
        "recent_checks": recent_detections(key.key_id, limit=20),
    }

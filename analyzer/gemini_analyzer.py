"""
Gemini Vision-based AI video detection — the BASE layer of the ensemble.

Improvements over v1:
- Stronger default model (gemini-2.5-flash) with automatic fallback chain
- 10 frames sampled as 5 temporal PAIRS (t, t+0.6s) → catches morphing/identity
  drift between consecutive frames, the strongest AI tell
- Continuous ai_probability output (better calibration than verdict+confidence)
- Second pass on uncertain results with different frames, averaged
"""
import os, base64, subprocess, tempfile, shutil, json, re, time
from dataclasses import dataclass, field
from typing import Optional
import urllib.request
import urllib.error

# Model fallback chain — first that responds wins (remembered per process).
# Override with GEMINI_MODEL env var.
_MODEL_CHAIN = [
    os.environ.get("GEMINI_MODEL", "").strip() or "gemini-2.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]
_working_model: Optional[str] = None

API_URL_TPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# In-memory cache: hash(video_path content) → GeminiResult
_CACHE: dict = {}

def _file_hash(path: str) -> str:
    """Fast hash of first 64KB of file for cache key."""
    try:
        import hashlib
        with open(path, "rb") as f:
            return hashlib.md5(f.read(65536)).hexdigest()
    except Exception:
        return ""

PROMPT = """You are the world's top forensic expert in detecting AI-generated video (Sora, Veo 3, Kling 2, Runway Gen-4, Pika, Hailuo, Wan, HeyGen avatars, etc. — 2026-era tools).

You are given frames sampled as CONSECUTIVE PAIRS: Pair 1 = (A,B) ~0.6s apart, Pair 2 = (A,B), etc. Compare within each pair — temporal consistency is the strongest signal.

STRONG AI INDICATORS:
- Between pair frames: objects/limbs/text/background details that morph, appear, vanish, or change identity
- Skin waxy/plastic, no pores; eyes glassy or asymmetric reflections
- Hands/fingers wrong count or impossible anatomy; hair merging into background
- Garbled or morphing text; logos that warp
- Physics-defying lighting/shadows; motion too perfectly smooth (no camera micro-shake)
- Face like a high-quality 3D render; over-coherent "cinematic" look everywhere

MODERN-TOOL NOTES (2026): top models produce very clean output — absence of classic artifacts is NOT proof of real. In that case judge: micro-shake, sensor noise pattern, natural messiness, imperfect framing, motion blur direction consistency.

NOT AI (normal for real social video): compression blocking, motion blur, grain/noise (real-camera sign), imperfect lighting, beauty filters.

AI EDITING on real footage: face swap edges/skin-tone mismatch, unnatural compositing seams, AI background replacement.

Respond ONLY with this JSON (no markdown):
{
  "ai_probability": 0.0 to 1.0,
  "verdict": "ai_generated" OR "ai_edited" OR "real",
  "confidence": 0.0 to 1.0,
  "reason": "specific visual evidence, under 90 chars",
  "artifacts": ["short artifact descriptions, max 4"]
}

CALIBRATION for ai_probability:
- 0.95+: multiple clear artifacts incl. temporal morphing
- 0.75-0.9: one or two clear artifacts
- 0.5-0.7: suspicious but not conclusive
- 0.2-0.4: looks real, minor doubt
- <0.1: clearly real camera footage (shake, noise, natural mess)
Never say 0.5 exactly — commit to a direction."""


@dataclass
class GeminiResult:
    verdict: str
    confidence: float
    reason: str
    frames_analyzed: int
    ai_probability: float = 0.5
    artifacts: list = field(default_factory=list)
    model_used: str = ""


def _video_duration(video_path: str) -> float:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    try:
        out = subprocess.check_output(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", video_path],
            stderr=subprocess.DEVNULL, timeout=8
        )
        return float(json.loads(out).get("format", {}).get("duration", 5.0))
    except Exception:
        return 5.0


def _grab_frame(video_path: str, t: float, out_path: str, scale: int = 640) -> Optional[str]:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    r = subprocess.run(
        [ffmpeg, "-ss", str(max(0.0, t)), "-i", video_path,
         "-vframes", "1", "-vf", f"scale={scale}:-1", "-q:v", "3",
         out_path, "-y", "-loglevel", "error"],
        capture_output=True, timeout=12
    )
    if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 500:
        with open(out_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode()
    return None


def _extract_frame_pairs(video_path: str, n_pairs: int = 5, offset_frac: float = 0.0) -> list:
    """Extract n_pairs of (t, t+0.6s) frames as base64 JPEGs. Returns flat list."""
    duration = _video_duration(video_path)
    pair_gap = 0.6 if duration > 3 else max(0.15, duration / 10)
    tmp_dir = tempfile.mkdtemp()
    frames = []
    try:
        for i in range(n_pairs):
            base_t = duration * ((i + 0.5 + offset_frac) % n_pairs) / n_pairs
            if base_t + pair_gap >= duration:
                base_t = max(0.0, duration - pair_gap - 0.1)
            a = _grab_frame(video_path, base_t, os.path.join(tmp_dir, f"p{i}a.jpg"))
            b = _grab_frame(video_path, base_t + pair_gap, os.path.join(tmp_dir, f"p{i}b.jpg"))
            if a and b:
                frames.append((i + 1, a, b))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return frames


def _call_gemini(api_key: str, pairs: list) -> Optional[dict]:
    """Single Gemini call over frame pairs. Returns parsed JSON dict or None."""
    parts = []
    for idx, a, b in pairs:
        parts.append({"text": f"Pair {idx} frame A:"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": a}})
        parts.append({"text": f"Pair {idx} frame B (+0.6s):"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b}})
    parts.append({"text": PROMPT})
    return _post_parts(api_key, parts)


def _post_parts(api_key: str, parts: list) -> Optional[dict]:
    """POST prebuilt content parts to Gemini, walking the model fallback chain."""
    global _working_model

    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.0}
    }).encode()

    models = [_working_model] if _working_model else []
    models += [m for m in _MODEL_CHAIN if m and m not in models]

    for model in models:
        url = API_URL_TPL.format(model=model) + f"?key={api_key}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = json.loads(resp.read())
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if not match:
                    return None
                parsed = json.loads(match.group())
                parsed["_model"] = model
                _working_model = model
                return parsed
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(3 * (attempt + 1))
                    continue
                if e.code in (400, 403, 404):
                    break  # model unavailable → try next in chain
                return None
            except Exception:
                return None
    return None


def _to_result(parsed: dict, n_frames: int) -> GeminiResult:
    verdict = parsed.get("verdict", "real")
    conf = float(parsed.get("confidence", 0.5))
    p = parsed.get("ai_probability")
    if p is None:
        # Older-style answer: derive probability from verdict+confidence
        p = conf if verdict in ("ai_generated", "ai_edited") else 1.0 - conf
    p = max(0.0, min(1.0, float(p)))
    return GeminiResult(
        verdict=verdict,
        confidence=conf,
        reason=parsed.get("reason", ""),
        frames_analyzed=n_frames,
        ai_probability=p,
        artifacts=list(parsed.get("artifacts") or [])[:4],
        model_used=parsed.get("_model", ""),
    )


def analyze_with_gemini(video_path: str) -> Optional[GeminiResult]:
    """Analyze video with Gemini Vision. Returns None if unavailable."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    key = _file_hash(video_path)
    if key and key in _CACHE:
        return _CACHE[key]

    pairs = _extract_frame_pairs(video_path, n_pairs=5)
    if len(pairs) < 2:
        return None

    parsed = _call_gemini(api_key, pairs)
    if not parsed:
        return None
    result = _to_result(parsed, n_frames=len(pairs) * 2)

    # Second opinion on uncertain results — different frame offsets, average
    if 0.35 < result.ai_probability < 0.70:
        pairs2 = _extract_frame_pairs(video_path, n_pairs=4, offset_frac=0.5)
        if len(pairs2) >= 2:
            parsed2 = _call_gemini(api_key, pairs2)
            if parsed2:
                r2 = _to_result(parsed2, n_frames=len(pairs2) * 2)
                avg_p = (result.ai_probability + r2.ai_probability) / 2
                # Keep the more descriptive reason
                if r2.ai_probability > result.ai_probability:
                    result.reason = r2.reason or result.reason
                    result.artifacts = r2.artifacts or result.artifacts
                result.ai_probability = avg_p
                result.verdict = (
                    "ai_generated" if avg_p >= 0.5 and result.verdict != "ai_edited"
                    else result.verdict if avg_p >= 0.5
                    else "real"
                )
                result.confidence = max(avg_p, 1 - avg_p)
                result.frames_analyzed += len(pairs2) * 2

    if key:
        _CACHE[key] = result
    return result


SINGLE_IMAGE_PROMPT = """You are the world's top forensic expert in detecting AI-generated imagery and video frames (Sora, Veo 3, Kling 2, Runway Gen-4, Pika, Midjourney, HeyGen avatars, etc. — 2026-era tools).

You are given ONE frame captured from a phone screen showing a social-media video (TikTok/YouTube/Instagram/etc.). The frame may include app UI (buttons, captions, progress bar) around the video — judge only the video content, ignore the UI chrome.

STRONG AI INDICATORS (single frame):
- Skin waxy/plastic, no pores; eyes glassy or asymmetric reflections
- Hands/fingers wrong count or impossible anatomy; hair merging into background
- Garbled or morphing text; logos/watermarks that warp
- Physics-defying lighting/shadows; over-coherent "cinematic" render look
- Faces like a high-quality 3D render; unnatural background coherence

NOT AI (normal for real social video): compression blocking, motion blur, grain/noise (real-camera sign), imperfect lighting, beauty filters.

A single frame is weaker evidence than video — be calibrated and do NOT over-flag. When the frame is a clean but ordinary photo/real scene, say real.

Respond ONLY with this JSON (no markdown):
{
  "ai_probability": 0.0 to 1.0,
  "verdict": "ai_generated" OR "ai_edited" OR "real",
  "confidence": 0.0 to 1.0,
  "reason": "specific visual evidence, under 90 chars",
  "artifacts": ["short artifact descriptions, max 4"]
}
Never say 0.5 exactly — commit to a direction."""


def analyze_image_with_gemini(image_b64: str) -> Optional[GeminiResult]:
    """
    Analyze a SINGLE screen-captured frame (base64 JPEG) with Gemini Vision.
    Used by the MediaProjection fallback, where no video URL/file is available.
    Returns None if the API key is missing or the call fails.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not image_b64:
        return None

    parts = [
        {"text": "Frame captured from screen:"},
        {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
        {"text": SINGLE_IMAGE_PROMPT},
    ]
    parsed = _post_parts(api_key, parts)
    if not parsed:
        return None
    return _to_result(parsed, n_frames=1)

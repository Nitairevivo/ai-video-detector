"""
Gemini Vision-based AI video detection.
Analyzes video frames visually using Google Gemini Flash — free tier.
Works even when TikTok/Instagram strips all metadata.
"""
import os, base64, subprocess, tempfile, shutil, json, re
from dataclasses import dataclass
from typing import Optional
import urllib.request

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent"

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

PROMPT = """You are the world's top forensic expert in detecting AI-generated video.

Analyze these frames from a social media video. Your job: determine if the VIDEO ITSELF was AI-generated (Sora, Kling, Runway, Pika, etc.) or is real camera footage.

STRONG AI INDICATORS (if you see ANY of these → high confidence AI):
- Skin that looks waxy, plastic, too smooth — no pores, no imperfections
- Eyes that look glassy, unnaturally bright, or have an "uncanny valley" feel
- Hair merging into background or behaving like liquid
- Hands with wrong number of fingers or impossible anatomy
- Background elements that shift or morph between frames
- Text in scene that is garbled, blurry, or morphing
- Lighting that doesn't follow physics (impossible shadows)
- Motion that is too perfectly smooth — no natural camera shake
- Faces that look like high-quality 3D renders
- Objects/people changing slightly between frames in unnatural ways

WEAKER AI INDICATORS (need multiple to be confident):
- Perfect lighting and composition with no real-world messiness
- Faces that look "too perfect" — like professional retouching but more extreme
- Motion that has no micro-vibrations (real cameras always shake slightly)
- Backgrounds that are too clean, too symmetric

NOT AI INDICATORS (these are normal for real videos):
- Pixelation or blocking from social media compression
- Motion blur from fast movement
- Grainy or noisy image (this is actually a REAL camera sign)
- Slightly imperfect lighting
- Normal beauty filters or makeup

Also detect AI EDITING on real footage:
- Face replacement with slightly wrong skin tone or sharp edges around face
- AI background replacement with unnatural compositing seams

Respond ONLY with this JSON (no markdown, no other text):
{
  "verdict": "ai_generated" OR "ai_edited" OR "real",
  "confidence": 0.0 to 1.0,
  "reason": "specific visual evidence, under 90 chars",
  "strongest_artifact": "the single most AI-like observation or null"
}

CONFIDENCE CALIBRATION:
- ai_generated with 0.9+: multiple clear artifacts, very sure
- ai_generated with 0.75: one or two clear artifacts
- real with 0.9+: clearly real camera footage
- real with 0.75: looks real but some doubt
- When genuinely uncertain: verdict=real, confidence=0.65"""


@dataclass
class GeminiResult:
    verdict: str
    confidence: float
    reason: str
    frames_analyzed: int


def _extract_frames(video_path: str, n: int = 6) -> list[str]:
    """Extract n frames as base64 JPEG strings."""
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    tmp_dir = tempfile.mkdtemp()
    frames_b64 = []

    try:
        out = subprocess.check_output(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", video_path],
            stderr=subprocess.DEVNULL, timeout=8
        )
        duration = float(json.loads(out).get("format", {}).get("duration", 5.0))
    except Exception:
        duration = 5.0

    for i in range(n):
        t = duration * (i + 0.5) / n
        out_path = os.path.join(tmp_dir, f"f{i}.jpg")
        r = subprocess.run(
            [ffmpeg, "-ss", str(t), "-i", video_path,
             "-vframes", "1", "-vf", "scale=480:-1", "-q:v", "4",
             out_path, "-y", "-loglevel", "error"],
            capture_output=True, timeout=12
        )
        if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 500:
            with open(out_path, "rb") as f:
                frames_b64.append(base64.standard_b64encode(f.read()).decode())

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return frames_b64


def analyze_with_gemini(video_path: str) -> Optional[GeminiResult]:
    """Analyze video with Gemini Vision. Returns None if unavailable."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    # Check cache first
    key = _file_hash(video_path)
    if key and key in _CACHE:
        return _CACHE[key]

    frames = _extract_frames(video_path, n=6)
    if len(frames) < 3:
        return None

    # Build Gemini request
    parts = []
    for i, b64 in enumerate(frames):
        parts.append({"text": f"Frame {i+1}:"})
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64
            }
        })
    parts.append({"text": PROMPT})

    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.1}
    }).encode()

    import time
    for attempt in range(3):
        try:
            url = f"{API_URL}?key={api_key}"
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            break  # success
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(3 * (attempt + 1))  # 3s, 6s
                continue
            return None
        except Exception:
            return None
    else:
        return None

    try:

        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        match = re.search(r'\{.*?\}', text, re.DOTALL)
        if not match:
            return None

        result = json.loads(match.group())
        gr = GeminiResult(
            verdict=result.get("verdict", "real"),
            confidence=float(result.get("confidence", 0.5)),
            reason=result.get("reason", ""),
            frames_analyzed=len(frames),
        )
        # Cache result
        if key:
            _CACHE[key] = gr
        return gr
    except Exception as e:
        return None

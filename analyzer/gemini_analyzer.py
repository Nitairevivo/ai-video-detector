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

PROMPT = """You are a forensic expert detecting AI-generated videos.

Analyze these video frames and determine if the video was created by an AI tool
(Sora, Kling, Runway, Pika, Luma, HeyGen, etc.) or captured by a real camera.

Look for AI generation signs:
- Plastic/waxy skin that looks too smooth
- Backgrounds that morph or blur unnaturally
- Hands with wrong fingers or impossible geometry
- Text that is garbled or morphing
- Eyes that are glassy or unnaturally symmetric
- Lighting inconsistencies (shadows going wrong direction)
- Hair that blends into background or behaves like liquid
- Objects appearing/disappearing between frames
- Motion that is too smooth with no natural camera shake
- Over-perfect composition with no real-world imperfections

Also check for AI editing on real footage:
- Face swaps (HeyGen, D-ID)
- AI-replaced backgrounds
- Extreme AI beauty filters

Respond ONLY with this JSON (no other text):
{
  "verdict": "ai_generated" OR "ai_edited" OR "real",
  "confidence": 0.0 to 1.0,
  "reason": "one sentence explanation under 80 chars"
}

IMPORTANT RULES:
- confidence means: how sure you are in your verdict (not probability of being AI)
- If verdict is "real", confidence=0.9 means 90% sure it's real
- Default to "real" when uncertain. Only say ai_generated when you see MULTIPLE clear AI artifacts
- Social media compression causes normal videos to look slightly unusual — this is NOT evidence of AI
- A beautiful, well-lit, stable shot is NOT AI evidence
- Only flag if you see: morphing skin, impossible geometry, objects merging, unnatural motion
- When in doubt: verdict="real", confidence=0.8"""


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

    try:
        url = f"{API_URL}?key={api_key}"
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        match = re.search(r'\{.*?\}', text, re.DOTALL)
        if not match:
            return None

        result = json.loads(match.group())
        return GeminiResult(
            verdict=result.get("verdict", "real"),
            confidence=float(result.get("confidence", 0.5)),
            reason=result.get("reason", ""),
            frames_analyzed=len(frames),
        )
    except Exception as e:
        return None

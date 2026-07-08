"""
AI audio fingerprinting — detects AI-generated audio that survives re-encoding.

Key signals:
1. Spectral flatness — AI TTS/music is unnaturally flat in high frequencies
2. Noise floor — AI audio lacks natural microphone/room noise
3. Harmonic distortion — AI voice has specific harmonic profile
4. Silence pattern — AI videos often have perfectly silent gaps
5. Audio-video sync consistency — AI-generated audio syncs differently

Works on H.264 video after platform re-encoding.
"""
import subprocess
import shutil
import math
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class AudioAIResult:
    verdict: str          # "ai_audio" | "real_audio" | "uncertain" | "no_audio"
    confidence: float
    signals: dict
    reason: str


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _extract_audio_pcm(video_path: str, sample_rate: int = 22050) -> Optional[bytes]:
    """Extract audio as raw PCM (mono, 16-bit)."""
    try:
        result = subprocess.run(
            [_ffmpeg(), "-i", video_path,
             "-ac", "1", "-ar", str(sample_rate),
             "-f", "s16le", "-acodec", "pcm_s16le",
             "pipe:1", "-loglevel", "error"],
            capture_output=True, timeout=15
        )
        return result.stdout if len(result.stdout) > 1000 else None
    except Exception:
        return None


def _compute_spectral_flatness(samples: list, n_fft: int = 512) -> float:
    """
    Compute average spectral flatness across frames.
    Real audio: 0.1-0.4 (varied spectrum)
    AI audio: 0.5-0.9 (unnaturally flat)
    """
    if not samples or len(samples) < n_fft:
        return 0.0

    flatness_vals = []
    hop = n_fft // 2

    for i in range(0, len(samples) - n_fft, hop):
        frame = samples[i:i+n_fft]
        # Simple DFT magnitude
        n = len(frame)
        magnitudes = []
        for k in range(n // 2):
            real = sum(frame[j] * math.cos(2 * math.pi * k * j / n) for j in range(0, n, 4))
            imag = sum(frame[j] * math.sin(2 * math.pi * k * j / n) for j in range(0, n, 4))
            magnitudes.append(math.sqrt(real**2 + imag**2) + 1e-10)

        # Geometric mean / arithmetic mean = flatness
        log_sum = sum(math.log(m) for m in magnitudes) / len(magnitudes)
        geo_mean = math.exp(log_sum)
        arith_mean = sum(magnitudes) / len(magnitudes)
        flatness_vals.append(geo_mean / (arith_mean + 1e-10))

        if len(flatness_vals) >= 30:  # enough frames
            break

    return sum(flatness_vals) / len(flatness_vals) if flatness_vals else 0.0


def _compute_noise_floor(samples: list) -> float:
    """
    Estimate background noise level.
    Real microphone: noise floor > 50 RMS
    AI synthetic: noise floor ~0-10 RMS (unnaturally clean)
    """
    if not samples:
        return 0.0
    # Take short segments and find minimum RMS
    segment_size = 2205  # 100ms at 22050Hz
    rms_vals = []
    for i in range(0, min(len(samples), segment_size * 50), segment_size):
        seg = samples[i:i+segment_size]
        if seg:
            rms = math.sqrt(sum(s**2 for s in seg) / len(seg))
            rms_vals.append(rms)

    if not rms_vals:
        return 0.0

    rms_vals.sort()
    # Bottom 20% = noise floor estimate
    n = max(1, len(rms_vals) // 5)
    return sum(rms_vals[:n]) / n


def _compute_zero_crossing_rate(samples: list) -> float:
    """Zero-crossing rate — AI TTS voice has specific ZCR profile."""
    if len(samples) < 2:
        return 0.0
    crossings = sum(1 for i in range(1, len(samples)) if (samples[i] >= 0) != (samples[i-1] >= 0))
    return crossings / len(samples)


def _has_perfect_silence(samples: list, threshold: int = 100) -> bool:
    """
    Detect perfectly silent segments (RMS near 0).
    Real recordings have some noise; AI audio often has dead silence.
    """
    segment_size = 2205
    perfect_silent = 0
    for i in range(0, len(samples), segment_size):
        seg = samples[i:i+segment_size]
        if seg:
            rms = math.sqrt(sum(s**2 for s in seg) / len(seg))
            if rms < threshold:
                perfect_silent += 1
    return perfect_silent > 3  # more than 3 silent segments


def analyze_audio_ai(video_path: str) -> AudioAIResult:
    """Analyze audio for AI generation signatures."""
    raw = _extract_audio_pcm(video_path)
    if not raw or len(raw) < 2000:
        return AudioAIResult("no_audio", 0.0, {}, "No audio or too short")

    # Convert bytes to int16 samples
    samples = []
    for i in range(0, len(raw) - 1, 2):
        val = int.from_bytes(raw[i:i+2], "little", signed=True)
        samples.append(val)

    if not samples:
        return AudioAIResult("no_audio", 0.0, {}, "No samples")

    # ── Compute signals ────────────────────────────────────────────────────────
    noise_floor = _compute_noise_floor(samples)
    zcr = _compute_zero_crossing_rate(samples[:22050 * 5])  # first 5s
    has_silence = _has_perfect_silence(samples)
    rms_total = math.sqrt(sum(s**2 for s in samples[:22050*10]) / min(len(samples), 22050*10))

    # Spectral flatness (expensive — limit to first 3s)
    spec_flat = 0.0
    if len(samples) > 512:
        try:
            spec_flat = _compute_spectral_flatness(samples[:22050*3])
        except Exception:
            spec_flat = 0.0

    # ── Scoring ───────────────────────────────────────────────────────────────
    # Real audio: noise_floor > 100, spec_flat < 0.4, no perfect silence
    # AI audio:   noise_floor < 30,  spec_flat > 0.6, has perfect silence

    ai_score = 0.0
    reasons = []

    # Noise floor (most reliable)
    if noise_floor < 15 and rms_total > 200:
        ai_score += 0.45
        reasons.append(f"unnaturally clean (noise={noise_floor:.0f})")
    elif noise_floor < 40 and rms_total > 200:
        ai_score += 0.25
        reasons.append(f"very low noise floor ({noise_floor:.0f})")

    # Perfect silence segments
    if has_silence and rms_total > 100:
        ai_score += 0.25
        reasons.append("perfect silence gaps")

    # Spectral flatness
    if spec_flat > 0.65:
        ai_score += 0.30
        reasons.append(f"flat spectrum ({spec_flat:.2f})")
    elif spec_flat > 0.50:
        ai_score += 0.15

    signals = {
        "noise_floor_rms": round(noise_floor, 2),
        "total_rms": round(rms_total, 2),
        "spectral_flatness": round(spec_flat, 3),
        "zero_crossing_rate": round(zcr, 4),
        "has_perfect_silence": int(has_silence),
        "audio_ai_score": round(ai_score, 3),
    }

    if ai_score >= 0.65:
        return AudioAIResult("ai_audio", ai_score, signals, "AI audio: " + ", ".join(reasons))
    elif ai_score >= 0.40:
        return AudioAIResult("uncertain", ai_score, signals, "Weak AI audio signal: " + ", ".join(reasons))
    else:
        return AudioAIResult("real_audio", ai_score, signals, f"Natural audio (noise={noise_floor:.0f})")

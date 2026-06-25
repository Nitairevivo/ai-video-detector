"""
Motion-based AI video detection.
Analyzes inter-frame motion patterns that survive TikTok/Instagram re-encoding.

Key insight from empirical calibration:
  Real camera (Schlossbergbahn): motion_std=2.26, temp_cv=0.59
  AI smooth (Sora-like):         motion_std=0.12, temp_cv=0.04
  AI temporal (AnimateDiff):     motion_std=0.16, temp_cv=0.15

Real cameras have high temporal VARIATION in motion (camera shake, natural movement).
AI videos have unnaturally smooth, consistent motion patterns.

These signals survive platform re-encoding because they are embedded in the
spatial-temporal structure of the video, not in the metadata.
"""
import subprocess
import shutil
import tempfile
import os
from dataclasses import dataclass
from typing import Optional

try:
    import numpy as np
    NUMPY = True
except ImportError:
    NUMPY = False


@dataclass
class MotionResult:
    verdict: str           # "ai_generated" | "real" | "uncertain"
    confidence: float
    method: str
    signals: dict


def _ffmpeg():
    return shutil.which("ffmpeg") or "ffmpeg"


def analyze_motion(video_path: str, n_frames: int = 16) -> MotionResult:
    """
    Analyze motion patterns to distinguish AI from real camera footage.

    Returns MotionResult with verdict and confidence.
    """
    if not NUMPY:
        return MotionResult("uncertain", 0.1, "numpy not available", {})

    try:
        result = subprocess.run(
            [_ffmpeg(), "-i", video_path, "-vframes", str(n_frames + 1),
             "-f", "rawvideo", "-pix_fmt", "gray",
             "-vf", "scale=64:36", "pipe:1", "-loglevel", "error"],
            capture_output=True, timeout=15
        )
        data = np.frombuffer(result.stdout, dtype=np.uint8)
        W, H = 64, 36
        total = W * H
        nf = len(data) // total
        if nf < 4:
            return MotionResult("uncertain", 0.1, "Too few frames", {})
        frames = data[:nf * total].reshape(nf, H, W).astype(np.float32)
    except Exception as e:
        return MotionResult("uncertain", 0.1, f"Frame extraction failed: {e}", {})

    # ── Compute motion features ───────────────────────────────────────────────
    motions = []
    for i in range(len(frames) - 1):
        diff = frames[i + 1] - frames[i]
        gx = np.gradient(diff, axis=1)
        gy = np.gradient(diff, axis=0)
        mag = np.sqrt(gx**2 + gy**2)
        motions.append({
            "mean": float(mag.mean()),
            "std": float(mag.std()),
            "max": float(mag.max()),
            "spatial_cv": float(mag.std() / (mag.mean() + 1e-8)),
        })

    if not motions:
        return MotionResult("uncertain", 0.1, "No motion data", {})

    # Temporal statistics
    means = np.array([m["mean"] for m in motions])
    maxes = np.array([m["max"] for m in motions])
    spatial_cvs = np.array([m["spatial_cv"] for m in motions])

    motion_mean = float(means.mean())
    motion_std = float(means.std())           # KEY: real >> AI
    motion_temporal_cv = float(means.std() / (means.mean() + 1e-8))  # KEY: real >> AI
    motion_max_std = float(maxes.std())
    spatial_consistency = float(spatial_cvs.mean())  # AI > real

    signals = {
        "motion_mean": round(motion_mean, 3),
        "motion_std": round(motion_std, 3),
        "motion_temporal_cv": round(motion_temporal_cv, 3),
        "motion_max_std": round(motion_max_std, 3),
        "spatial_consistency": round(spatial_consistency, 3),
        "frames_analyzed": len(frames),
    }

    # ── Decision ─────────────────────────────────────────────────────────────
    # Calibrated thresholds from real Wikimedia footage vs AI patterns:
    #   Real camera:  motion_std ≈ 2.0-3.0, temp_cv ≈ 0.30-0.60
    #   AI smooth:    motion_std ≈ 0.10-0.15, temp_cv ≈ 0.03-0.08
    #   AI temporal:  motion_std ≈ 0.14-0.18, temp_cv ≈ 0.12-0.18

    # Strong REAL signal
    if motion_std > 0.80 and motion_temporal_cv > 0.25:
        conf = min(0.06, 0.10 - motion_std * 0.01)
        return MotionResult("real", conf,
            f"Motion analysis: natural camera motion (std={motion_std:.2f}, cv={motion_temporal_cv:.3f})",
            signals)

    if motion_std > 0.50:
        return MotionResult("real", 0.08,
            f"Motion analysis: varied camera motion (std={motion_std:.2f})",
            signals)

    # Strong AI signal — unnaturally smooth
    if motion_std < 0.18 and motion_temporal_cv < 0.12:
        conf = min(0.92, 0.75 + (0.18 - motion_std) * 1.5 + (0.12 - motion_temporal_cv) * 2)
        return MotionResult("ai_generated", conf,
            f"Motion analysis: AI-smooth motion (std={motion_std:.2f}, cv={motion_temporal_cv:.3f})",
            signals)

    if motion_std < 0.25 and motion_temporal_cv < 0.20:
        conf = 0.65
        return MotionResult("ai_generated", conf,
            f"Motion analysis: suspiciously uniform motion (std={motion_std:.2f})",
            signals)

    # Moderate signals
    if motion_std < 0.35 and motion_temporal_cv < 0.25:
        return MotionResult("uncertain", 0.45,
            f"Motion analysis: possible AI (std={motion_std:.2f}, cv={motion_temporal_cv:.3f})",
            signals)

    return MotionResult("uncertain", 0.20,
        f"Motion analysis: inconclusive (std={motion_std:.2f}, cv={motion_temporal_cv:.3f})",
        signals)

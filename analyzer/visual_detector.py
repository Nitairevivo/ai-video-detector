"""
Unified visual AI detection module.
Combines frame analysis + ML model (if available) for maximum accuracy.
Works after TikTok/Instagram re-encoding.
"""
import os
import pickle
from dataclasses import dataclass
from typing import Optional

try:
    import numpy as np
    NUMPY = True
except ImportError:
    NUMPY = False

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "frame_model.pkl")
_model = None
_model_loaded = False


def _load_model():
    global _model, _model_loaded
    if _model_loaded:
        return _model
    _model_loaded = True
    try:
        if os.path.exists(MODEL_PATH):
            with open(MODEL_PATH, "rb") as f:
                _model = pickle.load(f)
    except Exception:
        # Model corrupt or incompatible — try rebuilding
        try:
            from analyzer.build_frame_model import build_model
            if build_model(verbose=False):
                with open(MODEL_PATH, "rb") as f:
                    _model = pickle.load(f)
        except Exception:
            _model = None
    return _model


@dataclass
class VisualDetectionResult:
    verdict: str        # "ai_generated" | "real" | "uncertain"
    confidence: float
    method: str
    signals: dict


def detect_visual(video_path: str) -> VisualDetectionResult:
    """
    Main visual detection function.
    Uses ML model if available, falls back to rule-based frame analysis.
    """
    from analyzer.frame_analyzer import (
        _get_frames, _local_block_variance, _inter_frame_diff,
        _fft_high_ratio, _temporal_consistency
    )

    if not NUMPY:
        return VisualDetectionResult("uncertain", 0.1, "numpy unavailable", {})

    frames = _get_frames(video_path, n=16, size="128x72")
    if frames is None or len(frames) < 4:
        return VisualDetectionResult("uncertain", 0.1, "could not extract frames", {})

    # Extract features
    local_var = _local_block_variance(frames)
    ifd_mean, ifd_std = _inter_frame_diff(frames)
    fft_ratio = _fft_high_ratio(frames)
    temp_cv = _temporal_consistency(frames)

    diffs = [float(np.abs(frames[i+1]-frames[i]).mean()) for i in range(len(frames)-1)]
    ifd_p10 = float(np.percentile(diffs, 10)) if diffs else 0
    ifd_p90 = float(np.percentile(diffs, 90)) if diffs else 0
    ifd_range = ifd_p90 - ifd_p10

    means = [float(f.mean()) for f in frames]
    brightness_std = float(np.std(means))

    all_bv = []
    for f in frames[:8]:
        h, w = f.shape
        for r in range(0, h-4, 4):
            for c in range(0, w-4, 4):
                all_bv.append(float(f[r:r+4, c:c+4].var()))
    lv_p5 = float(np.percentile(all_bv, 5)) if all_bv else 0
    lv_p50 = float(np.percentile(all_bv, 50)) if all_bv else 0
    lv_p95 = float(np.percentile(all_bv, 95)) if all_bv else 0

    signals = {
        "local_var": round(local_var, 1),
        "ifd_mean": round(ifd_mean, 3),
        "ifd_std": round(ifd_std, 3),
        "ifd_range": round(ifd_range, 3),
        "ifd_p10": round(ifd_p10, 3),
        "ifd_p90": round(ifd_p90, 3),
        "fft_ratio": round(fft_ratio, 4),
        "temp_cv": round(temp_cv, 4),
        "brightness_std": round(brightness_std, 3),
        "lv_p5": round(lv_p5, 2),
        "lv_p50": round(lv_p50, 2),
        "lv_p95": round(lv_p95, 2),
        "frames_analyzed": len(frames),
    }

    feature_vec = [
        local_var, ifd_mean, ifd_std, ifd_range, ifd_p10, ifd_p90,
        fft_ratio, temp_cv, brightness_std, lv_p5, lv_p50, lv_p95,
    ]

    # ── Try ML model first ────────────────────────────────────────────────────
    model = _load_model()
    if model is not None:
        try:
            prob = float(model.predict_proba([feature_vec])[0][1])
            signals["ml_prob"] = round(prob, 3)

            if prob >= 0.75:
                return VisualDetectionResult(
                    "ai_generated", prob,
                    f"ML visual model: {prob:.0%} AI probability (var={local_var:.0f}, cv={temp_cv:.3f})",
                    signals
                )
            elif prob <= 0.25:
                return VisualDetectionResult(
                    "real", 1 - prob,
                    f"ML visual model: {(1-prob):.0%} real probability (var={local_var:.0f})",
                    signals
                )
            else:
                # ML is uncertain — use rule-based for final decision
                pass
        except Exception:
            pass

    # ── Rule-based fallback ───────────────────────────────────────────────────
    # Based on calibration from real camera footage:
    # Real camera: var=600-800, temp_cv=0.40-0.60, fft=0.20-0.26
    # AI smooth:   var=90-250,  temp_cv=0.05-0.15, fft=0.05-0.12
    # AI sharp:    var=350-500, temp_cv=0.05-0.15, fft=0.20-0.35

    # Strong REAL signal
    if local_var >= 580 and temp_cv >= 0.35:
        return VisualDetectionResult("real", 0.05, f"Frame analysis: real camera signature (var={local_var:.0f}, cv={temp_cv:.3f})", signals)
    if local_var >= 500 and temp_cv >= 0.40:
        return VisualDetectionResult("real", 0.06, f"Frame analysis: high natural variance + motion", signals)
    if ifd_mean >= 6.0 and temp_cv >= 0.30:
        return VisualDetectionResult("real", 0.07, f"Frame analysis: high natural temporal variation", signals)

    # Strong AI signal
    if local_var < 120 and temp_cv < 0.15:
        conf = min(0.90, 0.72 + (0.15 - temp_cv) * 0.8)
        return VisualDetectionResult("ai_generated", conf, f"Frame analysis: AI-smooth (var={local_var:.0f}, cv={temp_cv:.3f})", signals)
    if local_var < 180 and temp_cv < 0.12 and fft_ratio < 0.10:
        return VisualDetectionResult("ai_generated", 0.75, f"Frame analysis: AI diffusion pattern (smooth+clean spectrum)", signals)
    if local_var < 200 and temp_cv < 0.10:
        return VisualDetectionResult("ai_generated", 0.68, f"Frame analysis: suspiciously smooth and uniform", signals)

    # Moderate AI signals
    if temp_cv < 0.08 and ifd_mean < 2.0:
        return VisualDetectionResult("ai_generated", 0.65, f"Frame analysis: unnaturally static motion (cv={temp_cv:.3f})", signals)
    if local_var < 250 and temp_cv < 0.15 and fft_ratio < 0.12:
        return VisualDetectionResult("uncertain", 0.52, f"Frame analysis: possible AI (var={local_var:.0f}, cv={temp_cv:.3f})", signals)

    return VisualDetectionResult("uncertain", 0.15, f"Frame analysis: inconclusive (var={local_var:.0f}, cv={temp_cv:.3f}, fft={fft_ratio:.3f})", signals)

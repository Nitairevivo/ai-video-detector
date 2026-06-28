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


def detect_visual_with_motion(video_path: str) -> VisualDetectionResult:
    """
    Combined detection: frame analysis + motion analysis + ensemble voting.
    Significantly higher accuracy than each signal alone.
    """
    # Run frame analysis
    frame_result = detect_visual(video_path)

    # Run motion analysis
    try:
        from analyzer.motion_analyzer import analyze_motion
        motion = analyze_motion(video_path)
    except Exception:
        motion = None

    if motion is None:
        return frame_result

    signals = {**frame_result.signals, **{f"motion_{k}": v for k, v in motion.signals.items()}}

    # ── Ensemble voting ────────────────────────────────────────────────────────
    frame_ai = frame_result.verdict == "ai_generated"
    motion_ai = motion.verdict == "ai_generated"
    frame_real = frame_result.verdict == "real"
    motion_real = motion.verdict == "real"

    # Both say REAL → very confident it's real (cameras are distinctive)
    if frame_real and motion_real:
        return VisualDetectionResult("real", 0.04,
            f"Ensemble: frame + motion both real ({frame_result.method[:30]})",
            signals)

    # Both say AI → high confidence
    if frame_ai and motion_ai:
        combined = (frame_result.confidence + motion.confidence) / 2
        combined = min(0.95, combined * 1.1)  # boost ensemble agreement
        return VisualDetectionResult("ai_generated", combined,
            f"Ensemble: frame + motion both AI — {motion.method[:40]}",
            signals)

    # Motion says AI strongly, frame uncertain → trust motion
    if motion_ai and motion.confidence >= 0.75 and not frame_real:
        return VisualDetectionResult("ai_generated", motion.confidence * 0.85,
            f"Ensemble: motion analysis — {motion.method[:50]}",
            signals)

    # Frame says AI strongly, motion uncertain → trust frame
    if frame_ai and frame_result.confidence >= 0.70 and not motion_real:
        return VisualDetectionResult("ai_generated", frame_result.confidence * 0.85,
            f"Ensemble: frame analysis — {frame_result.method[:50]}",
            signals)

    # Motion says real strongly → override uncertain frame
    if motion_real and motion.confidence <= 0.10:
        return VisualDetectionResult("real", 0.06,
            f"Ensemble: motion confirms real camera ({motion.method[:40]})",
            signals)

    # Disagreement or both uncertain
    if frame_result.verdict == "uncertain" and motion.verdict == "uncertain":
        best_conf = max(frame_result.confidence, motion.confidence)
        return VisualDetectionResult("uncertain", best_conf * 0.7,
            f"Ensemble: inconclusive (frame={frame_result.confidence:.0%}, motion={motion.confidence:.0%})",
            signals)

    # Default: use whichever is more confident
    if frame_result.confidence >= motion.confidence:
        return VisualDetectionResult(frame_result.verdict, frame_result.confidence,
            frame_result.method, signals)
    else:
        return VisualDetectionResult(motion.verdict, motion.confidence,
            motion.method, signals)


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

    # Motion features (strongest signal for TikTok re-encoded content)
    try:
        from analyzer.motion_analyzer import analyze_motion
        mot = analyze_motion(video_path)
        motion_std = mot.signals.get("motion_std", 0.0)
        motion_cv = mot.signals.get("motion_temporal_cv", 0.0)
        signals["motion_std"] = round(motion_std, 3)
        signals["motion_cv"] = round(motion_cv, 3)
    except Exception:
        motion_std = motion_cv = 0.0

    feature_vec = [
        local_var, ifd_mean, ifd_std, ifd_range, ifd_p10, ifd_p90,
        fft_ratio, temp_cv, brightness_std, lv_p5, lv_p50, lv_p95,
        motion_std, motion_cv,
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
    # Calibration — raw footage vs platform re-encoded:
    # Real camera (raw/Wikimedia):      var=600-800, temp_cv=0.40-0.60, fft=0.20-0.26
    # Real camera (TikTok/YouTube):     var=180-280, temp_cv=0.15-0.35
    # AI smooth (re-encoded):           var=90-150,  temp_cv=0.05-0.15, fft=0.05-0.12
    # AI over-sharp (re-encoded):       var=300-500, temp_cv=0.05-0.15, fft=0.20-0.35

    # Strong REAL signal — re-encoded platform content (TikTok/YouTube/Instagram)
    # Key: real cameras land at var=190-310 after re-encoding; AI-smooth is <150
    if local_var >= 190 and local_var <= 310 and temp_cv >= 0.18:
        return VisualDetectionResult("real", 0.07, f"Frame analysis: re-encoded camera signature (var={local_var:.0f}, cv={temp_cv:.3f})", signals)
    # Strong REAL signal — raw/unencoded footage
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

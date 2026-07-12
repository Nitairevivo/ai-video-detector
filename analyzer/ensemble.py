"""
Gemini-base detection ensemble.

Architecture (the order matters):
  0. Hard overrides  — platform AIGC label / definitive metadata signatures.
     These end the analysis immediately (fast + near-certain).
  1. BASE: Gemini Vision — continuous ai_probability over temporal frame pairs.
  2. Supporting layers, fused in log-odds space with per-layer weights:
       metadata/container signatures, frame-ML classifier,
       visual detector, audio AI analysis.
  3. Agreement calibration — independent layers agreeing with the base sharpen
     the confidence; strong disagreement pulls it toward uncertainty.
  4. Camera-origin guard — real-camera metadata caps AI confidence unless the
     visual evidence is overwhelming (deepfake case).

All heavy layers run in parallel threads; the fast paths skip them entirely.
"""
import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EnsembleResult:
    verdict: str                 # ai_generated | ai_edited | real
    confidence: float            # AI probability, 0..1
    method: str
    layers: dict = field(default_factory=dict)   # per-layer probabilities for transparency
    gemini_reason: str = ""
    gemini_artifacts: list = field(default_factory=list)


def _logit(p: float) -> float:
    p = min(0.995, max(0.005, p))
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


_UNSET = "__unset__"


def analyze_ensemble(tmp_path: str, meta_result, ml_prob: Optional[float],
                     use_gemini: bool = True, gemini_result=_UNSET) -> EnsembleResult:
    """
    meta_result: FeatureResult from extract_features (already computed by caller).
    ml_prob:     trained frame-ML probability or None.
    gemini_result: pass a precomputed Gemini result (or None) to skip the internal
                   call — lets the caller overlap Gemini with feature extraction.
    """
    meta_conf = float(meta_result.confidence)
    camera_origin = bool(meta_result.signals.get("camera_origin_detected"))
    layers = {}

    # ── 0. Hard override: definitive metadata signatures ─────────────────────
    if meta_conf >= 0.90:
        return EnsembleResult(
            verdict=meta_result.verdict if meta_result.verdict != "real" else "ai_generated",
            confidence=meta_conf,
            method=meta_result.method,
            layers={"metadata": meta_conf},
        )

    # ── 1+2. Run heavy layers in parallel ────────────────────────────────────
    gemini = vis = audio = None
    have_gemini = gemini_result is not _UNSET
    with ThreadPoolExecutor(max_workers=3) as ex:
        # Only start Gemini here if the caller didn't already run it (overlapped).
        fut_g = ex.submit(_run_gemini, tmp_path) if (use_gemini and not have_gemini) else None
        fut_v = ex.submit(_run_visual, tmp_path)
        fut_a = ex.submit(_run_audio, tmp_path)
        if fut_g:
            gemini = fut_g.result()
        elif have_gemini:
            gemini = gemini_result
        vis = fut_v.result()
        audio = fut_a.result()

    # Collect (probability, weight) votes
    votes = []

    # BASE: Gemini — the anchor when available
    if gemini is not None:
        layers["gemini"] = round(gemini.ai_probability, 3)
        votes.append((gemini.ai_probability, 1.0))

    # Metadata: one-sided evidence. Low confidence = "no signal", not "real".
    if camera_origin:
        layers["metadata_camera"] = 0.05
        votes.append((0.05, 1.1))
    elif meta_conf >= 0.5:
        layers["metadata"] = meta_conf
        votes.append((meta_conf, 0.9))
    elif meta_conf >= 0.15:
        layers["metadata"] = meta_conf
        votes.append((0.5 + meta_conf, 0.4))

    # Frame-ML classifier: only in its informative region (tiny training set)
    if ml_prob is not None and (ml_prob >= 0.70 or ml_prob <= 0.30):
        layers["frame_ml"] = round(ml_prob, 3)
        votes.append((ml_prob, 0.45))

    # Visual detector (rules + motion)
    if vis is not None:
        if vis.verdict == "ai_generated" and vis.confidence >= 0.62:
            layers["visual"] = round(vis.confidence, 3)
            votes.append((vis.confidence, 0.45))
        elif vis.verdict == "real" and vis.confidence >= 0.90:
            layers["visual"] = round(1 - vis.confidence, 3)
            votes.append((0.08, 0.45))

    # Audio AI
    if audio is not None and getattr(audio, "verdict", "") == "ai_audio" and audio.confidence >= 0.65:
        layers["audio"] = round(audio.confidence, 3)
        votes.append((0.5 + audio.confidence * 0.35, 0.3))

    # ── Fusion ────────────────────────────────────────────────────────────────
    if not votes:
        # Nothing informative — trust the (weak) metadata result as-is
        return EnsembleResult(
            verdict="real", confidence=max(0.04, meta_conf),
            method=meta_result.method, layers=layers,
        )

    total_w = sum(w for _, w in votes)
    fused_logit = sum(_logit(p) * w for p, w in votes) / total_w
    p = _sigmoid(fused_logit)

    # ── 3. Agreement calibration ─────────────────────────────────────────────
    direction_ai = p >= 0.5
    strong_agree = sum(
        1 for lp, w in votes
        if abs(lp - 0.5) > 0.15 and (lp >= 0.5) == direction_ai
    )
    strong_oppose = sum(
        1 for lp, w in votes
        if abs(lp - 0.5) > 0.20 and (lp >= 0.5) != direction_ai and w >= 0.45
    )
    if strong_agree >= 2 and strong_oppose == 0:
        p = p + (1 - p) * 0.30 if direction_ai else p * 0.70
    elif strong_oppose >= 1:
        p = 0.5 + (p - 0.5) * 0.6  # conflicting evidence → hedge

    # ── 3b. Single-witness rule ───────────────────────────────────────────────
    # An AI verdict must never rest on Gemini ALONE while a measured layer
    # (frame-ML / visual / metadata) actively disagrees. Gemini misreads chaotic
    # real-world motion (flour, water spray, confetti) as temporal morphing —
    # a lone 0.9 from it must not flip a real video to "AI" (false positive =
    # the worst failure mode). Corroboration from any other AI-leaning layer
    # restores full weight.
    if p >= 0.5:
        gemini_says_ai = gemini is not None and gemini.ai_probability >= 0.5
        support_ai = [
            k for k, lp in layers.items()
            if k != "gemini" and isinstance(lp, (int, float)) and lp >= 0.5
        ]
        oppose_real = [
            k for k, lp in layers.items()
            if k != "gemini" and isinstance(lp, (int, float)) and lp <= 0.15
        ]
        if gemini_says_ai and not support_ai and oppose_real:
            # Gemini is the only accuser and hard evidence points real → hold
            # below the AI threshold but keep it visibly "suspicious".
            p = min(p, 0.45)

    # ── 4. Camera-origin guard (deepfakes can still exceed it) ───────────────
    if camera_origin and p < 0.90:
        p = min(p, 0.35)

    # ── Verdict ───────────────────────────────────────────────────────────────
    if gemini is not None and gemini.verdict == "ai_edited" and 0.35 <= p:
        verdict = "ai_edited"
        p = max(p, min(0.85, gemini.ai_probability))
    elif p >= 0.5:
        verdict = "ai_generated"
    else:
        verdict = "real"

    # ── Method string ─────────────────────────────────────────────────────────
    parts = []
    if gemini is not None:
        parts.append(f"Gemini base {gemini.ai_probability:.0%}" +
                     (f" ({gemini.reason})" if gemini.reason else ""))
    support = [k for k in layers if k not in ("gemini",)]
    if support:
        parts.append("layers: " + ", ".join(support))
    method = "Ensemble — " + "; ".join(parts) if parts else meta_result.method

    return EnsembleResult(
        verdict=verdict,
        confidence=round(min(0.97, max(0.02, p)), 4),
        method=method,
        layers=layers,
        gemini_reason=getattr(gemini, "reason", "") if gemini else "",
        gemini_artifacts=list(getattr(gemini, "artifacts", []) or []) if gemini else [],
    )


# ── Layer runners (each swallows its own failures) ────────────────────────────

def _run_gemini(tmp_path: str):
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    try:
        from analyzer.gemini_analyzer import analyze_with_gemini
        g = analyze_with_gemini(tmp_path)
        if g and g.frames_analyzed >= 4:
            return g
    except Exception:
        pass
    return None


def _run_visual(tmp_path: str):
    try:
        from analyzer.visual_detector import detect_visual_with_motion
        return detect_visual_with_motion(tmp_path)
    except Exception:
        return None


def _run_audio(tmp_path: str):
    try:
        from analyzer.audio_analyzer_ai import analyze_audio_ai
        return analyze_audio_ai(tmp_path)
    except Exception:
        return None

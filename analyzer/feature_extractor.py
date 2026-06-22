"""
Combines all analysis results into a unified feature vector for the ML classifier.
Also produces a rule-based confidence score as a fallback when the ML model
has not been trained yet.
"""
from dataclasses import dataclass, asdict
from typing import Optional
import numpy as np

from .metadata_reader import MetadataResult, read_metadata
from .codec_analyzer import CodecFeatures, analyze_codec
from .container_parser import ContainerFeatures, parse_container
from .audio_analyzer import AudioFeatures, analyze_audio


@dataclass
class DetectionResult:
    file_path: str
    is_ai: bool
    confidence: float           # 0.0 - 1.0
    ai_tool: Optional[str]      # named tool if detected
    method: str                 # how it was determined
    signals: dict               # individual signal values
    feature_vector: list        # numeric vector for ML model


def extract_features(file_path: str) -> DetectionResult:
    meta = read_metadata(file_path)
    codec = analyze_codec(file_path)
    container = parse_container(file_path)
    audio = analyze_audio(file_path)

    signals = _collect_signals(meta, codec, container, audio)
    feature_vector = _build_vector(signals)
    confidence, method, ai_tool = _rule_based_decision(meta, codec, container, audio, signals)

    return DetectionResult(
        file_path=file_path,
        is_ai=confidence >= 0.5,
        confidence=confidence,
        ai_tool=ai_tool,
        method=method,
        signals=signals,
        feature_vector=feature_vector,
    )


def _collect_signals(
    meta: MetadataResult,
    codec: CodecFeatures,
    container: ContainerFeatures,
    audio: AudioFeatures,
) -> dict:
    return {
        # Metadata signals
        "has_ai_metadata_tag": int(meta.ai_tool_detected is not None),
        "has_ai_exclusive_encoder": int(meta.has_ai_exclusive_encoder),
        "has_c2pa": int(meta.has_c2pa),
        "c2pa_is_ai": int(meta.c2pa_is_ai),
        "software_tag_present": int(meta.software_tag is not None),

        # Codec signals
        "pts_uniformity": codec.pts_uniformity,
        "pts_jitter_std": codec.pts_jitter_std,
        "keyframe_interval_std": codec.keyframe_interval_std,
        "keyframe_interval_mean": codec.keyframe_interval_mean,
        "frame_size_cv": codec.frame_size_cv,
        "frame_size_skewness": codec.frame_size_skewness,
        "codec_ai_score": codec.codec_ai_score,
        "has_b_frames": int(codec.has_b_frames),
        "ref_frames": codec.ref_frames,

        # Container signals
        "moov_before_mdat": int(container.moov_before_mdat),
        "has_fragmented_mp4": int(container.has_fragmented_mp4),
        "has_proprietary_box": int(len(container.proprietary_boxes) > 0),
        "container_ai_score": container.container_ai_score,

        # Audio signals
        "has_audio": int(audio.has_audio),
        "is_fully_silent": int(audio.is_fully_silent),
        "silence_ratio": audio.silence_ratio,
        "audio_rms_cv": audio.audio_rms_cv or 0.0,
        "audio_ai_score": audio.audio_ai_score,

        # Scene & entropy signals
        "scene_change_rate": codec.scene_change_rate,
        "scene_change_uniformity": codec.scene_change_uniformity,
        "entropy_mean": codec.entropy_mean,
        "entropy_std": codec.entropy_std,
        "entropy_cv": codec.entropy_cv,

        # File-level
        "file_size_mb": meta.file_size_bytes / (1024 * 1024),
        "duration_seconds": meta.duration_seconds or 0.0,
        "bitrate_kbps": meta.bitrate_kbps or 0.0,
        "fps": meta.fps or 0.0,
        "width": meta.width or 0,
        "height": meta.height or 0,
    }


def _build_vector(signals: dict) -> list:
    # Fixed-order numeric vector for the ML model
    keys = [
        "has_ai_metadata_tag", "has_ai_exclusive_encoder", "has_c2pa",
        "c2pa_is_ai", "software_tag_present",
        "pts_uniformity", "pts_jitter_std",
        "keyframe_interval_std", "keyframe_interval_mean",
        "frame_size_cv", "frame_size_skewness",
        "codec_ai_score",
        "has_b_frames", "ref_frames",
        "moov_before_mdat", "has_fragmented_mp4", "has_proprietary_box",
        "container_ai_score",
        "has_audio", "is_fully_silent", "silence_ratio", "audio_rms_cv", "audio_ai_score",
        "scene_change_rate", "scene_change_uniformity",
        "entropy_mean", "entropy_std", "entropy_cv",
        # NOTE: file_size_mb, duration_seconds, bitrate_kbps, width, height intentionally
        # excluded from ML — they correlate with dataset source, not AI generation.
        "fps",
    ]
    return [float(signals.get(k, 0.0)) for k in keys]


def _rule_based_decision(
    meta: MetadataResult,
    codec: CodecFeatures,
    container: ContainerFeatures,
    audio: AudioFeatures,
    signals: dict,
) -> tuple[float, str, Optional[str]]:
    """
    Deterministic rule cascade — ordered from most confident to least.
    Returns (confidence, method_description, ai_tool_name).
    """
    ai_tool = meta.ai_tool_detected or container.ai_tool_from_box

    # Tier 1: Definitive markers
    if meta.c2pa_is_ai:
        return 0.99, "C2PA cryptographic proof", ai_tool

    if meta.ai_tool_detected:
        return 0.97, f"Metadata tag: '{meta.ai_tool_detected}'", ai_tool

    if meta.has_ai_exclusive_encoder:
        return 0.95, "AI-exclusive encoder detected", ai_tool

    if container.ai_tool_from_box and 'C2PA' not in container.ai_tool_from_box:
        return 0.93, f"Proprietary container box: {container.ai_tool_from_box}", ai_tool

    # Tier 2: Strong structural signals
    if container.container_ai_score > 0.70:
        return 0.82, "Container structure matches AI tool pattern", ai_tool

    if meta.has_c2pa:
        # C2PA present but not flagged as AI — still suspicious
        return 0.60, "C2PA provenance present (origin unverified)", None

    # Tier 3: Frame timing — AI video = perfectly uniform PTS (pts_uniformity near 1.0)
    if codec.pts_uniformity >= 0.97:
        return 0.88, "Perfect frame timing uniformity (AI signature)", ai_tool

    # Tier 4: Very low entropy = AI-generated frames look uniform / synthetic
    if codec.entropy_mean > 0 and codec.entropy_mean < 2.0:
        return 0.85, "Extremely low frame entropy (AI synthetic pattern)", ai_tool

    # Tier 5: Audio signals (lower weight — many real videos have no audio)
    if not audio.has_audio and codec.pts_uniformity >= 0.90:
        return 0.72, "No audio + uniform frame timing (AI pattern)", ai_tool
    if audio.is_fully_silent and codec.pts_uniformity >= 0.90:
        return 0.70, "Silent audio + uniform frame timing (AI pattern)", ai_tool

    # Tier 6: Statistical codec + audio signals
    combined = (
        codec.codec_ai_score * 0.45
        + container.container_ai_score * 0.25
        + audio.audio_ai_score * 0.30
    )
    if combined > 0.70:
        return combined, "Statistical fingerprint: codec + audio patterns", ai_tool
    if combined > 0.50:
        return combined, "Weak statistical signal — inconclusive", None

    # Tier 7: Insufficient evidence
    return max(0.05, combined), "No AI markers detected", None

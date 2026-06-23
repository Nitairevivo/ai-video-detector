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
    verdict: str = "real"       # "ai_generated" | "ai_edited" | "real"
    edit_tool: Optional[str] = None  # editing tool if AI-edited


def extract_features(file_path: str) -> DetectionResult:
    meta = read_metadata(file_path)
    codec = analyze_codec(file_path)
    container = parse_container(file_path)
    audio = analyze_audio(file_path)

    signals = _collect_signals(meta, codec, container, audio)
    feature_vector = _build_vector(signals)
    confidence, method, ai_tool = _rule_based_decision(meta, codec, container, audio, signals)

    # Determine verdict — priority: hard metadata > edit tool > statistical
    edit_tool = _detect_ai_edit_tool(meta)
    has_hard_ai_evidence = bool(
        meta.c2pa_is_ai or
        meta.ai_tool_detected or
        meta.has_ai_exclusive_encoder or
        (container.ai_tool_from_box and "C2PA" not in (container.ai_tool_from_box or ""))
    )
    if has_hard_ai_evidence:
        verdict = "ai_generated"
    elif edit_tool:
        # Edit tool detected → ai_edited regardless of statistical score
        verdict = "ai_edited"
    elif confidence >= 0.5:
        verdict = "ai_generated"
    else:
        verdict = "real"

    return DetectionResult(
        file_path=file_path,
        is_ai=confidence >= 0.5,
        confidence=confidence,
        ai_tool=ai_tool,
        method=method,
        signals=signals,
        feature_vector=feature_vector,
        verdict=verdict,
        edit_tool=edit_tool,
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

    POLICY: Only flag as AI-GENERATED when the video itself was created by an AI tool.
    Videos edited with AI effects (CapCut filters, AI audio, etc.) on real footage
    must NOT be flagged — we require hard evidence of AI generation, not just
    statistical patterns that re-encoding also produces.
    """
    ai_tool = meta.ai_tool_detected or container.ai_tool_from_box

    # ── Tier 1: Definitive proof — always AI-generated ────────────────────────

    if meta.c2pa_is_ai:
        return 0.99, "C2PA cryptographic proof of AI generation", ai_tool

    if meta.ai_tool_detected:
        return 0.97, f"AI generation tool in metadata: '{meta.ai_tool_detected}'", ai_tool

    if meta.has_ai_exclusive_encoder:
        return 0.95, "AI-exclusive encoder signature detected", ai_tool

    if container.ai_tool_from_box and "C2PA" not in container.ai_tool_from_box:
        return 0.93, f"AI tool signature in container: {container.ai_tool_from_box}", ai_tool

    # ── Camera/real-origin check — strong evidence this is real footage ────────
    # If camera EXIF markers are present, the base footage is real.
    # AI editing on top doesn't make it AI-generated.
    has_camera_origin = _has_camera_origin(meta)
    if has_camera_origin:
        return 0.06, "Camera origin markers detected — real footage", None

    # ── Tier 2: Strong container patterns (require HIGH score) ────────────────
    # Only fire if the container pattern is very distinctive of AI tools.
    # Threshold raised from 0.70 → 0.88 to avoid re-encoded real videos.
    if container.container_ai_score > 0.88:
        return 0.85, "Container structure strongly matches AI generation pattern", ai_tool

    # C2PA present but not explicitly AI — unverified origin, lower signal only
    if meta.has_c2pa:
        return 0.45, "C2PA provenance present — origin unverified", None

    # ── Tier 3: Frame timing — require BOTH uniformity AND additional signal ──
    # pts_uniformity alone is NOT enough: re-encoded videos also have perfect timing.
    # We require uniformity + at least one more independent signal.
    # entropy_mean < 2.5 can occur in classic/music/animation even for real videos —
    # raise threshold to avoid flagging these.
    timing_very_uniform = codec.pts_uniformity >= 0.98
    entropy_very_low = codec.entropy_mean > 0 and codec.entropy_mean < 1.2  # was 1.5
    audio_ai_strong = audio.audio_ai_score > 0.75
    codec_ai_strong = codec.codec_ai_score > 0.75

    # Statistical signals are unreliable for videos without any identifying metadata.
    # Re-encoded real videos (via FFmpeg, editing software, platform processing)
    # also produce perfect timing and high codec_ai_score.
    # We ONLY use statistical signals if the video has SOME metadata that doesn't
    # indicate a real camera origin — i.e., it's suspicious but not confirmed.
    has_any_metadata = bool(
        meta.software_tag or meta.encoder_tag or
        meta.creation_tool or meta.comment_field
    )

    if has_any_metadata and not has_camera_origin:
        # Some metadata present but not from a known camera — apply statistical signals
        independent_signals = sum([
            timing_very_uniform,
            entropy_very_low,
            audio_ai_strong,
            codec_ai_strong,
            container.container_ai_score > 0.65,
        ])

        if independent_signals >= 3:
            return 0.80, "Multiple independent AI generation signals (timing + entropy + codec)", ai_tool
        if independent_signals == 2:
            if timing_very_uniform and entropy_very_low:
                return 0.75, "Perfect frame timing + very low entropy (AI generation pattern)", ai_tool

    # ── Tier 4: Combined statistical — only fire at very high threshold ───────
    combined = (
        codec.codec_ai_score * 0.45
        + container.container_ai_score * 0.25
        + audio.audio_ai_score * 0.30
    )
    if not has_camera_origin and combined > 0.88:
        return combined, "Strong combined statistical fingerprint", ai_tool

    # ── No strong evidence — not AI-generated ────────────────────────────────
    return max(0.04, combined * 0.3), "No AI generation markers detected", None


def _has_camera_origin(meta: MetadataResult) -> bool:
    """
    Returns True if the video has markers indicating it was captured by a real camera
    (phone, DSLR, action cam, screen recorder from a real-footage app, etc.).
    These markers mean the BASE footage is real, even if AI effects were applied later.
    """
    CAMERA_SOFTWARE = {
        "iphone", "samsung", "pixel", "android", "gopro",
        "dji", "sony", "canon", "nikon", "fujifilm",
        "snapchat", "instagram", "tiktok camera",  # native camera capture
        "com.apple.photo", "avfoundation",
        "xiaomi", "huawei", "oppo", "vivo",
    }
    CAMERA_ENCODERS = {
        "apple videotoolbox", "mediacodec", "qualcomm",  # hardware encoders (cameras/phones)
        "com.apple.avfoundation",
    }

    sw = (meta.software_tag or "").lower()
    enc = (meta.encoder_tag or "").lower()
    tool = (meta.creation_tool or "").lower()
    all_text = " ".join([sw, enc, tool, " ".join(meta.all_tags.values())]).lower()

    for marker in CAMERA_SOFTWARE:
        if marker in all_text:
            return True
    for marker in CAMERA_ENCODERS:
        if marker in enc:
            return True

    # GPS or camera EXIF fields strongly indicate real-world capture
    camera_exif_keys = {"gps_latitude", "gps_longitude", "location", "com.apple.quicktime.location.iso6709"}
    if camera_exif_keys & set(meta.all_tags.keys()):
        return True

    return False


def _detect_ai_edit_tool(meta: MetadataResult) -> Optional[str]:
    """
    Detects AI editing tools applied to real footage.
    Returns tool name if AI editing found, None otherwise.
    These are tools that EDIT real videos with AI — not tools that GENERATE video.
    """
    AI_EDIT_TOOLS = {
        "capcut": "CapCut AI",
        "cap cut": "CapCut AI",
        "jianying": "CapCut AI",        # CapCut's Chinese name
        "adobe premiere": "Adobe Premiere AI",
        "adobe firefly": "Adobe Firefly",
        "adobe sensei": "Adobe Sensei AI",
        "davinci": "DaVinci Resolve AI",
        "resolve": "DaVinci Resolve AI",
        "wondershare": "Wondershare Filmora AI",
        "filmora": "Filmora AI",
        "kinemaster": "KineMaster AI",
        "powerdirector": "PowerDirector AI",
        "inshot": "InShot AI",
        "vllo": "VLLO AI",
        "splice": "Splice AI",
        "videoleap": "Videoleap AI",
        "topaz": "Topaz Video AI",
        "enhancefox": "AI Enhancer",
        "remini": "Remini AI",
        "meitu": "Meitu AI",
        "facetune": "Facetune AI",
        "snow": "SNOW AI",
        "b612": "B612 AI",
        "youcam": "YouCam AI",
        "lensa": "Lensa AI",
        "photoroom": "PhotoRoom AI",
        "cutout.pro": "Cutout.pro AI",
        "deepl": "AI Translation",
        "mubert": "Mubert AI Music",
        "suno": "Suno AI Music",
        "elevenlabs": "ElevenLabs AI Voice",
        "speechify": "Speechify AI",
    }

    all_text = " ".join([
        (meta.software_tag or ""),
        (meta.encoder_tag or ""),
        (meta.creation_tool or ""),
        (meta.comment_field or ""),
        " ".join(str(v) for v in meta.all_tags.values()),
    ]).lower()

    for keyword, tool_name in AI_EDIT_TOOLS.items():
        if keyword in all_text:
            return tool_name

    return None

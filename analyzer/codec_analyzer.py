"""
Analyzes encoding parameters and statistical patterns from the video bitstream.
AI-generated videos have characteristic codec fingerprints that differ from
camera-captured footage even after re-encoding.
"""
import subprocess
import json
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from .metadata_reader import FFPROBE


@dataclass
class CodecFeatures:
    # Frame-level statistics
    frame_count: int = 0
    keyframe_count: int = 0
    keyframe_interval_mean: float = 0.0
    keyframe_interval_std: float = 0.0

    # Bitrate distribution
    frame_sizes: list = field(default_factory=list)
    frame_size_mean: float = 0.0
    frame_size_std: float = 0.0
    frame_size_cv: float = 0.0          # coefficient of variation
    frame_size_skewness: float = 0.0

    # Timing uniformity (AI = near-perfect, real = slight jitter)
    pts_deltas: list = field(default_factory=list)
    pts_uniformity: float = 0.0         # 1.0 = perfectly uniform
    pts_jitter_std: float = 0.0

    # Codec-level signals
    codec_profile: Optional[str] = None
    codec_level: Optional[str] = None
    color_space: Optional[str] = None
    color_primaries: Optional[str] = None
    pixel_format: Optional[str] = None

    # Quality distribution
    psnr_mean: Optional[float] = None
    has_b_frames: bool = False
    ref_frames: int = 0

    # Scene change analysis
    scene_change_count: int = 0
    scene_change_rate: float = 0.0      # scene changes per second
    scene_change_uniformity: float = 0.0  # 1.0 = evenly spaced

    # Frame entropy (visual complexity)
    entropy_mean: float = 0.0
    entropy_std: float = 0.0
    entropy_cv: float = 0.0             # low CV = AI (too uniform visually)

    # Computed AI likelihood from codec features only
    codec_ai_score: float = 0.0


# Profiles/pixel formats commonly associated with AI generation pipelines
AI_PIXEL_FORMATS = {"yuv420p", "yuv420p10le"}  # too generic alone, used in combo
AI_SUSPICIOUS_COMBOS = [
    ("h264", "High", "yuv420p"),
    ("hevc", "Main", "yuv420p"),
    ("av1", "Main", "yuv420p"),
]

MAX_FRAMES_TO_SAMPLE = 120  # ~4 seconds at 30fps — enough for statistical patterns


def analyze_codec(file_path: str) -> CodecFeatures:
    features = CodecFeatures()
    _extract_stream_info(file_path, features)
    _extract_frame_data(file_path, features)
    _extract_scene_and_entropy(file_path, features)
    _compute_ai_score(features)
    return features


def _extract_stream_info(file_path: str, features: CodecFeatures):
    cmd = [
        FFPROBE, "-v", "quiet",
        "-select_streams", "v:0",
        "-show_streams",
        "-print_format", "json",
        file_path
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=8)
        data = json.loads(output)
        streams = data.get("streams", [])
        if not streams:
            return
        s = streams[0]
        features.codec_profile = s.get("profile")
        features.codec_level = str(s.get("level", ""))
        features.color_space = s.get("color_space")
        features.color_primaries = s.get("color_primaries")
        features.pixel_format = s.get("pix_fmt")
        features.has_b_frames = bool(s.get("has_b_frames", 0))
        features.ref_frames = s.get("refs", 0)
    except Exception:
        pass


def _extract_frame_data(file_path: str, features: CodecFeatures):
    cmd = [
        FFPROBE, "-v", "quiet",
        "-select_streams", "v:0",
        "-show_frames",
        "-show_entries", "frame=pkt_size,pts_time,key_frame,pict_type",
        "-print_format", "json",
        "-read_intervals", f"%+#{MAX_FRAMES_TO_SAMPLE}",
        file_path
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10)
        data = json.loads(output)
    except Exception:
        return

    frames = data.get("frames", [])
    if len(frames) < 10:
        return

    features.frame_count = len(frames)
    sizes = []
    pts_times = []
    keyframe_positions = []

    for i, frame in enumerate(frames):
        size = frame.get("pkt_size")
        pts = frame.get("pts_time")
        is_key = frame.get("key_frame", 0)

        if size is not None:
            sizes.append(int(size))
        if pts is not None:
            try:
                pts_times.append(float(pts))
            except ValueError:
                pass
        if is_key:
            keyframe_positions.append(i)

    features.frame_sizes = sizes
    features.keyframe_count = len(keyframe_positions)

    if sizes:
        arr = np.array(sizes, dtype=np.float64)
        features.frame_size_mean = float(np.mean(arr))
        features.frame_size_std = float(np.std(arr))
        features.frame_size_cv = (
            features.frame_size_std / features.frame_size_mean
            if features.frame_size_mean > 0 else 0.0
        )
        # Skewness: AI video tends to be more symmetric
        if features.frame_size_std > 0:
            features.frame_size_skewness = float(
                np.mean(((arr - features.frame_size_mean) / features.frame_size_std) ** 3)
            )

    if len(keyframe_positions) >= 2:
        intervals = np.diff(keyframe_positions).astype(np.float64)
        features.keyframe_interval_mean = float(np.mean(intervals))
        features.keyframe_interval_std = float(np.std(intervals))

    if len(pts_times) >= 2:
        deltas = np.diff(pts_times)
        features.pts_deltas = deltas.tolist()
        mean_delta = np.mean(deltas)
        if mean_delta > 0:
            normalized = deltas / mean_delta
            features.pts_jitter_std = float(np.std(normalized))
            # Uniformity: 1 = perfect, 0 = chaotic
            features.pts_uniformity = float(max(0, 1 - min(features.pts_jitter_std * 10, 1)))


def _extract_scene_and_entropy(file_path: str, features: CodecFeatures):
    """
    Detects scene changes and measures per-frame visual entropy.
    AI videos: few scene changes, very uniform entropy.
    Real footage: irregular scene changes, variable entropy.
    """
    cmd = [
        "ffmpeg", "-i", file_path,
        "-vf", f"select='gt(scene,0.3)',metadata=print:file=-",
        "-frames:v", str(MAX_FRAMES_TO_SAMPLE),
        "-an", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=20
        )
        import re
        scene_times = [float(m.group(1)) for m in re.finditer(r"pts_time:([\d.]+)", result.stderr)]
        features.scene_change_count = len(scene_times)

        duration_hint = None
        dur_match = re.search(r"Duration:\s*([\d:]+\.[\d]+)", result.stderr)
        if dur_match:
            parts = dur_match.group(1).split(":")
            duration_hint = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

        if duration_hint and duration_hint > 0:
            features.scene_change_rate = features.scene_change_count / duration_hint

        if len(scene_times) >= 2:
            gaps = np.diff(scene_times)
            mean_gap = np.mean(gaps)
            if mean_gap > 0:
                uniformity = 1 - min(np.std(gaps) / mean_gap, 1.0)
                features.scene_change_uniformity = float(uniformity)
    except Exception:
        pass

    # Frame entropy via lavfi
    entropy_cmd = [
        "ffprobe", "-v", "quiet",
        "-f", "lavfi",
        "-i", f"movie={file_path},entropy",
        "-show_frames",
        "-show_entries", "frame_tags=lavfi.entropy.entropy.normal.Y",
        "-print_format", "json",
        "-read_intervals", f"%+#{MAX_FRAMES_TO_SAMPLE}",
    ]
    try:
        output = subprocess.check_output(entropy_cmd, stderr=subprocess.DEVNULL, timeout=15)
        data = json.loads(output)
        entropies = []
        for frame in data.get("frames", []):
            tags = frame.get("tags", {})
            e = tags.get("lavfi.entropy.entropy.normal.Y")
            if e is not None:
                try:
                    entropies.append(float(e))
                except ValueError:
                    pass

        if len(entropies) >= 5:
            arr = np.array(entropies)
            features.entropy_mean = float(np.mean(arr))
            features.entropy_std = float(np.std(arr))
            if features.entropy_mean > 0:
                features.entropy_cv = features.entropy_std / features.entropy_mean
    except Exception:
        pass


def _compute_ai_score(features: CodecFeatures):
    score = 0.0
    weight_total = 0.0

    # Perfect frame timing = strong AI signal
    if features.pts_uniformity > 0:
        timing_score = features.pts_uniformity
        score += timing_score * 0.35
        weight_total += 0.35

    # Very uniform keyframe intervals = AI signal
    if features.keyframe_interval_mean > 0:
        kf_uniformity = max(0, 1 - (features.keyframe_interval_std / features.keyframe_interval_mean))
        score += kf_uniformity * 0.20
        weight_total += 0.20

    # Low frame size coefficient of variation = AI signal (too consistent)
    if features.frame_size_cv > 0:
        cv_score = max(0, 1 - features.frame_size_cv * 2)
        score += cv_score * 0.20
        weight_total += 0.20

    # Low skewness in frame sizes = AI signal
    if features.frame_size_skewness != 0:
        skew_score = max(0, 1 - abs(features.frame_size_skewness) / 3)
        score += skew_score * 0.25
        weight_total += 0.25

    # Low entropy CV = frames are too visually uniform = AI signal
    if features.entropy_cv > 0:
        entropy_score = max(0, 1 - features.entropy_cv * 8)
        score += entropy_score * 0.20
        weight_total += 0.20

    # Few or zero scene changes relative to duration = AI signal
    if features.scene_change_rate >= 0:
        # Real videos: ~0.3-2 scene changes/sec; AI: often 0-0.1
        scene_score = max(0, 1 - features.scene_change_rate * 3)
        score += scene_score * 0.15
        weight_total += 0.15

    if weight_total > 0:
        features.codec_ai_score = score / weight_total

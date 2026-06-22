"""
Analyzes audio track characteristics.
Many AI video generators produce no audio, or TTS audio with specific patterns.
Audio absence is a strong AI signal for tools like Sora, Runway, Kling.
"""
import subprocess
import json
import numpy as np
from dataclasses import dataclass
from typing import Optional
from .metadata_reader import FFPROBE


@dataclass
class AudioFeatures:
    has_audio: bool = False
    audio_codec: Optional[str] = None
    audio_sample_rate: Optional[int] = None
    audio_channels: Optional[int] = None
    audio_bitrate_kbps: Optional[float] = None
    audio_duration: Optional[float] = None

    # Silence analysis
    is_fully_silent: bool = False
    silence_ratio: float = 0.0       # fraction of audio that is silent

    # Statistical patterns
    audio_rms_mean: Optional[float] = None
    audio_rms_std: Optional[float] = None
    audio_rms_cv: Optional[float] = None  # coefficient of variation

    audio_ai_score: float = 0.0


def analyze_audio(file_path: str) -> AudioFeatures:
    features = AudioFeatures()
    _extract_audio_stream(file_path, features)
    if features.has_audio:
        _analyze_silence(file_path, features)
        _analyze_rms(file_path, features)
    _compute_audio_score(features)
    return features


def _extract_audio_stream(file_path: str, features: AudioFeatures):
    cmd = [
        FFPROBE, "-v", "quiet",
        "-select_streams", "a:0",
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
        features.has_audio = True
        features.audio_codec = s.get("codec_name")
        features.audio_sample_rate = int(s.get("sample_rate", 0)) or None
        features.audio_channels = s.get("channels")
        features.audio_duration = float(s.get("duration", 0)) or None
        br = s.get("bit_rate")
        if br:
            features.audio_bitrate_kbps = float(br) / 1000
    except Exception:
        pass


def _analyze_silence(file_path: str, features: AudioFeatures):
    """Detect silence using ffmpeg silencedetect filter."""
    cmd = [
        "ffmpeg", "-i", file_path,
        "-af", "silencedetect=noise=-50dB:d=0.5",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
        output = result.stderr
        silence_durations = []
        import re
        for m in re.finditer(r"silence_duration:\s*([\d.]+)", output):
            silence_durations.append(float(m.group(1)))

        total_silence = sum(silence_durations)
        duration = features.audio_duration or 1.0
        features.silence_ratio = min(total_silence / duration, 1.0)
        features.is_fully_silent = features.silence_ratio > 0.95
    except Exception:
        pass


def _analyze_rms(file_path: str, features: AudioFeatures):
    """Sample RMS volume in 1-second chunks using ffprobe astats."""
    cmd = [
        FFPROBE, "-v", "quiet",
        "-f", "lavfi",
        "-i", f"amovie={file_path},astats=length=1:metadata=1",
        "-show_frames",
        "-show_entries", "frame_tags=lavfi.astats.Overall.RMS_level",
        "-print_format", "json",
        "-read_intervals", "%+30",  # first 30 seconds
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=15)
        data = json.loads(output)
        rms_values = []
        for frame in data.get("frames", []):
            tags = frame.get("tags", {})
            rms = tags.get("lavfi.astats.Overall.RMS_level")
            if rms and rms != "-inf":
                try:
                    rms_values.append(float(rms))
                except ValueError:
                    pass

        if len(rms_values) >= 3:
            arr = np.array(rms_values)
            features.audio_rms_mean = float(np.mean(arr))
            features.audio_rms_std = float(np.std(arr))
            if features.audio_rms_mean != 0:
                features.audio_rms_cv = features.audio_rms_std / abs(features.audio_rms_mean)
    except Exception:
        pass


def _compute_audio_score(features: AudioFeatures) -> None:
    """
    Higher score = more likely AI.
    No audio = strong AI signal (many generators don't add audio).
    Fully silent audio = strong AI signal.
    Very uniform RMS = AI TTS signal.
    """
    if not features.has_audio:
        # Weak signal alone — many real videos have no audio (timelapses, clips)
        features.audio_ai_score = 0.45
        return

    score = 0.0

    if features.is_fully_silent:
        score = max(score, 0.85)
    elif features.silence_ratio > 0.5:
        score = max(score, 0.60)

    # Very uniform RMS = AI TTS or generated audio
    if features.audio_rms_cv is not None:
        if features.audio_rms_cv < 0.05:
            score = max(score, 0.70)
        elif features.audio_rms_cv < 0.15:
            score = max(score, 0.40)

    features.audio_ai_score = score

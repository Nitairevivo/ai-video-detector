"""
Reads all metadata from video files without decoding frames.
Extracts software tags, encoder info, creation tools, and C2PA credentials.
"""
import subprocess
import json
import struct
import os
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


def _ffprobe_path() -> str:
    # Prefer system ffprobe, then imageio-ffmpeg bundled binary
    system = shutil.which("ffprobe")
    if system:
        return system
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        # ffprobe sits next to ffmpeg
        probe = Path(exe).parent / "ffprobe"
        if probe.exists():
            return str(probe)
    except Exception:
        pass
    return "ffprobe"  # fallback, will error if not found


FFPROBE = _ffprobe_path()


KNOWN_AI_TOOLS = {
    # OpenAI
    "sora": "OpenAI Sora",
    # Runway
    "runway": "Runway",
    "gen-2": "Runway Gen-2",
    "gen-3": "Runway Gen-3",
    "gen-4": "Runway Gen-4",
    # Pika
    "pika": "Pika Labs",
    # Kling / Kuaishou
    "kling": "Kuaishou Kling",
    "kuaishou": "Kuaishou Kling",
    # Luma
    "luma": "Luma AI",
    "dream machine": "Luma Dream Machine",
    # MiniMax
    "hailuo": "MiniMax Hailuo",
    "minimax": "MiniMax",
    # Google
    "veo": "Google Veo",
    "lumiere": "Google Lumiere",
    # Stability AI
    "stable video": "Stability AI SVD",
    "stablevideo": "Stability AI SVD",
    "svd": "Stability AI SVD",
    # Wan / Alibaba
    "wan2": "Wan 2.0",
    "wan 2": "Wan 2.0",
    "wan-video": "Wan Video",
    "tongyi": "Tongyi Wanxiang",
    # Haiper
    "haiper": "Haiper",
    # CogVideo / Zhipu
    "cogvideo": "CogVideo",
    "cogvideox": "CogVideoX",
    # Open source
    "animatediff": "AnimateDiff",
    "modelscope": "ModelScope",
    "zeroscope": "ZeroScope",
    "videocrafter": "VideoCrafter",
    "show-1": "Show-1",
    "lavie": "LaVie",
    "open-sora": "Open-Sora",
    "opensora": "Open-Sora",
    "mochi": "Genmo Mochi",
    "hunyuan": "Tencent HunyuanVideo",
    "stepvideo": "StepVideo",
    "seaweed": "ByteDance Seaweed",
    # Avatar / deepfake tools
    "synthesia": "Synthesia",
    "heygen": "HeyGen",
    "d-id": "D-ID",
    "deepbrain": "DeepBrain AI",
    "creatify": "Creatify",
    "invideo": "InVideo AI",
    # Generic markers
    "text2video": "Text2Video",
    "ai-generated": "AI Generated",
    "aigc": "AIGC",
    "ai_generated": "AI Generated",
}

# Encoders that are exclusively used by AI video tools
AI_EXCLUSIVE_ENCODERS = {
    "libsvtav1_sora",
    "sora_encoder",
    "runway_vae",
    "pika_codec",
}


@dataclass
class MetadataResult:
    file_path: str
    file_size_bytes: int
    container_format: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    bitrate_kbps: Optional[float] = None

    # Suspicious fields
    software_tag: Optional[str] = None
    encoder_tag: Optional[str] = None
    creation_tool: Optional[str] = None
    comment_field: Optional[str] = None
    all_tags: dict = field(default_factory=dict)

    # Detection signals
    has_c2pa: bool = False
    c2pa_is_ai: bool = False
    ai_tool_detected: Optional[str] = None
    has_ai_exclusive_encoder: bool = False

    # Anomalies
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    encoded_date: Optional[str] = None


def read_metadata(file_path: str) -> MetadataResult:
    path = Path(file_path)
    result = MetadataResult(
        file_path=str(path),
        file_size_bytes=path.stat().st_size,
    )

    _read_ffprobe(file_path, result)
    _scan_for_ai_tags(result)
    _check_c2pa(file_path, result)

    return result


def _read_ffprobe(file_path: str, result: MetadataResult):
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        file_path
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=8)
        data = json.loads(output)
    except Exception:
        return

    fmt = data.get("format", {})
    tags = fmt.get("tags", {})
    result.container_format = fmt.get("format_name")
    result.duration_seconds = float(fmt.get("duration", 0)) or None
    result.bitrate_kbps = float(fmt.get("bit_rate", 0)) / 1000 or None

    # Collect all tags (case-insensitive keys lowercased)
    result.all_tags = {k.lower(): v for k, v in tags.items()}
    result.software_tag = tags.get("software") or tags.get("Software")
    result.encoder_tag = tags.get("encoder") or tags.get("Encoder")
    result.creation_tool = tags.get("creation_tool") or tags.get("tool")
    result.comment_field = tags.get("comment") or tags.get("Comment")
    result.creation_date = tags.get("creation_time")
    result.encoded_date = tags.get("encoded_date")

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video":
            result.video_codec = stream.get("codec_name")
            result.width = stream.get("width")
            result.height = stream.get("height")
            r_fps = stream.get("r_frame_rate", "0/1")
            try:
                num, den = r_fps.split("/")
                result.fps = round(float(num) / float(den), 3)
            except Exception:
                pass
            stream_tags = stream.get("tags", {})
            result.all_tags.update({k.lower(): v for k, v in stream_tags.items()})
        elif codec_type == "audio":
            result.audio_codec = stream.get("codec_name")


def _scan_for_ai_tags(result: MetadataResult):
    all_text = " ".join(
        str(v).lower() for v in result.all_tags.values()
        if v
    )
    # Also check named fields
    for field_val in [result.software_tag, result.encoder_tag,
                       result.creation_tool, result.comment_field]:
        if field_val:
            all_text += " " + field_val.lower()

    for keyword, tool_name in KNOWN_AI_TOOLS.items():
        if keyword in all_text:
            result.ai_tool_detected = tool_name
            break

    encoder = (result.encoder_tag or "").lower()
    if encoder in AI_EXCLUSIVE_ENCODERS:
        result.has_ai_exclusive_encoder = True


def _check_c2pa(file_path: str, result: MetadataResult):
    """
    C2PA (Content Credentials) embedded as UUID/JUMBF box in MP4.
    AI tools can place this anywhere in the file, so we scan in chunks.
    Also scans for binary AI tool signatures embedded in the bitstream.
    """
    C2PA_UUID = b'\xd8\xfe\xc3\xd6\x1b\x0e\x48\x3c\x92\x97\x58\x28\x87\x7e\xc4\x81'
    CHUNK = 65536  # 64KB per read
    MAX_SCAN = 5 * 1024 * 1024  # scan up to 5MB

    # Binary signatures embedded by AI tools in bitstream (not just metadata)
    BINARY_SIGS: list[tuple[bytes, str]] = [
        (b'c2pa.ai', None),
        (b'ai.generated', None),
        (b'openai-sora', "OpenAI Sora"),
        (b'sora_watermark', "OpenAI Sora"),
        (b'runway_watermark', "Runway"),
        (b'pika_watermark', "Pika Labs"),
        (b'kling_watermark', "Kuaishou Kling"),
        (b'luma_watermark', "Luma AI"),
        (b'heygen.com', "HeyGen"),
        (b'synthesia', "Synthesia"),
        (b'com.apple.quicktime.software', None),
        (b'AIGC', None),
    ]

    try:
        scanned = 0
        with open(file_path, "rb") as f:
            while scanned < MAX_SCAN:
                chunk = f.read(CHUNK)
                if not chunk:
                    break

                if C2PA_UUID in chunk:
                    result.has_c2pa = True
                if b'c2pa.ai' in chunk or b'ai.generated' in chunk:
                    result.c2pa_is_ai = True
                    result.has_c2pa = True

                for sig, tool_name in BINARY_SIGS:
                    if sig in chunk:
                        if tool_name and not result.ai_tool_detected:
                            result.ai_tool_detected = tool_name
                        if b'AIGC' in chunk and not result.ai_tool_detected:
                            result.ai_tool_detected = "AI Generated"

                scanned += len(chunk)
    except Exception:
        pass

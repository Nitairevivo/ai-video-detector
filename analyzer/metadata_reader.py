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
    "runwayml": "Runway",
    "gen-2": "Runway Gen-2",
    "gen-3": "Runway Gen-3",
    "gen-4": "Runway Gen-4",
    "gen4": "Runway Gen-4",
    "runway gen": "Runway",
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
    # Generic text2video tools (specific enough)
    "text2video": "Text2Video",
    # Newer tools (2024-2025)
    "veo": "Google Veo",
    "veo2": "Google Veo 2",
    "veo 2": "Google Veo 2",
    "imagen video": "Google Imagen Video",
    "lumiere": "Google Lumiere",
    "seaweed": "ByteDance Seaweed",
    "step-video": "StepVideo",
    "stepvideo": "StepVideo",
    "cogvideo": "CogVideo",
    "cogvideox": "CogVideoX",
    "cog-video": "CogVideo",
    "wan 2": "Wan 2.0",
    "wan2.0": "Wan 2.0",
    "wanvideo": "Wan Video",
    "genmo": "Genmo Mochi",
    "mochi-1": "Genmo Mochi",
    "haiper": "Haiper",
    "haiper.ai": "Haiper",
    "morph studio": "Morph Studio",
    "morphstudio": "Morph Studio",
    "kaiber": "Kaiber AI",
    "kaiber.ai": "Kaiber AI",
    "decohere": "Decohere AI",
    "higgsfield": "Higgsfield AI",
    "pixverse": "PixVerse",
    "pixverse.ai": "PixVerse",
    "ltx-video": "Lightricks LTX",
    "ltxvideo": "Lightricks LTX",
    "lightricks": "Lightricks LTX",
    "sora-turbo": "OpenAI Sora",
    "sora_turbo": "OpenAI Sora",
    "runway-gen4": "Runway Gen-4",
    "gen4": "Runway Gen-4",
    "pika-2": "Pika Labs 2.0",
    "pika2": "Pika Labs 2.0",
    "kling-2": "Kuaishou Kling 2.0",
    "kling2": "Kuaishou Kling 2.0",
    "hailuo-02": "MiniMax Hailuo 02",
    "minimax-02": "MiniMax 02",
    "vidu": "Shengshu Vidu",
    "shengshu": "Shengshu Vidu",
    "skyreels": "SkyReels",
    "jogg.ai": "Jogg AI",
    "jogg-ai": "Jogg AI",
    "fliki": "Fliki AI",
    "fliki.ai": "Fliki AI",
    "deepmotion": "DeepMotion",
    "genspark": "Genspark AI",
    # Avatar/Presenter tools
    "d-id": "D-ID",
    "d_id": "D-ID",
    "did.com": "D-ID",
    "deepbrain": "DeepBrain AI",
    "aistudios": "DeepBrain AI",
    "rephrase.ai": "Rephrase AI",
    "elai.io": "Elai AI",
    "colossyan": "Colossyan",
    "steve.ai": "Steve AI",
    "vidnoz": "Vidnoz AI",
    "pictory": "Pictory AI",
    "simpleshow": "Simpleshow AI",
    # NOTE: "aigc", "ai-generated", "ai_generated" REMOVED —
    # TikTok adds "AIGC" to ALL videos (including real footage) as a platform label.
}

# Encoders that are exclusively used by AI video tools
AI_EXCLUSIVE_ENCODERS = {
    "libsvtav1_sora",
    "sora_encoder",
    "runway_vae",
    "pika_codec",
}

# AI tool native resolutions: these exact pixel dimensions are produced by specific
# AI generation tools and are rarely used by real cameras.
# (width, height) → (tool_name, confidence)
AI_NATIVE_RESOLUTIONS: dict[tuple[int, int], tuple[str, float]] = {
    # Luma Dream Machine — extremely distinctive non-standard dimensions
    (1360, 752): ("Luma Dream Machine", 0.92),
    (752, 1360): ("Luma Dream Machine", 0.92),
    (848, 480):  ("Luma/AI tool",       0.72),
    (480, 848):  ("Luma/AI tool",       0.72),
    # Pika Labs — uses unusual 1088 width (mod-64, not mod-16 like cameras)
    (1088, 832): ("Pika Labs", 0.90),
    (832, 1088): ("Pika Labs", 0.90),
    (1344, 768): ("Pika Labs", 0.78),
    (768, 1344): ("Pika Labs", 0.78),
    # Runway Gen-3 — very unusual ultra-widescreen preset
    (1584, 672): ("Runway", 0.92),
    (672, 1584): ("Runway", 0.92),
    (1280, 768): ("Runway/AI tool", 0.62),
    (768, 1280): ("Runway/AI tool", 0.62),
    # Kling / Hailuo — 704-wide portrait (never a standard camera resolution)
    (704, 1280): ("Kling/Hailuo", 0.75),
    (1280, 704): ("Kling/Hailuo", 0.75),
    (960, 544):  ("AI tool", 0.65),
    (544, 960):  ("AI tool", 0.65),
    # Wan 2.0 / open-source models
    (832, 480):  ("Wan/open-source AI", 0.70),
    (480, 832):  ("Wan/open-source AI", 0.70),
    # Square outputs — only AI tools and screen recordings produce these
    (512, 512):  ("AI tool (square)", 0.82),
    (768, 768):  ("AI tool (square)", 0.82),
    (1024, 1024):("AI tool (square)", 0.85),
}

# Exact video durations produced by AI generation tools (±DURATION_TOL seconds).
# Real camera footage almost never ends at precisely these times.
AI_TYPICAL_DURATIONS = {2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 9.0, 10.0, 15.0, 16.0, 20.0}
DURATION_TOL = 0.12  # ±120 ms


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
    c2pa_is_ai: bool = False                 # valid signed manifest claims AI
    c2pa_verified: bool = False              # manifest signature validated
    c2pa_digital_source_type: Optional[str] = None
    c2pa_claim_generator: Optional[str] = None
    ai_tool_detected: Optional[str] = None
    has_ai_exclusive_encoder: bool = False
    # IPTC DigitalSourceType (open provenance standard, written into XMP by Adobe,
    # platforms and many AI tools) — detected by byte scan, no dependency.
    iptc_digital_source_type: Optional[str] = None   # e.g. "trainedAlgorithmicMedia"
    synthetic_media_marker: bool = False             # IPTC marker declares AI/synthetic
    capture_origin_marker: bool = False              # IPTC marker declares real capture (digitalCapture)

    # Resolution fingerprint (survives re-encoding)
    resolution_ai_tool: Optional[str] = None
    resolution_ai_confidence: float = 0.0

    # Duration fingerprint (survives re-encoding)
    duration_is_ai_typical: bool = False

    # Anomalies
    creation_date: Optional[str] = None
    modification_date: Optional[str] = None
    encoded_date: Optional[str] = None

    # Stripped / platform signals
    metadata_is_stripped: bool = False      # all tags suspiciously absent — possible re-mux
    platform_reencoded: bool = False        # detected platform re-encode (TikTok/IG/etc.)
    platform_name: Optional[str] = None    # which platform re-encoded it
    too_short_for_analysis: bool = False    # duration < 2s — unreliable stats
    probe_failed: bool = False              # ffprobe itself failed — emptiness is NOT evidence


# Platform re-encoders: these services strip original metadata and re-encode
PLATFORM_SIGNATURES = {
    # TikTok
    "bytedance": "TikTok",
    "tiktok": "TikTok",
    "musically": "TikTok",
    "com.zhiliaoapp": "TikTok",
    # Instagram / Facebook
    "instagram": "Instagram",
    "facebook": "Facebook",
    "com.instagram": "Instagram",
    "com.facebook": "Facebook",
    # YouTube
    "youtube": "YouTube",
    "googlevideo": "YouTube",
    # WhatsApp
    "whatsapp": "WhatsApp",
    # Twitter/X
    "twitter": "Twitter/X",
    "twimg": "Twitter/X",
    # Snapchat
    "snapchat": "Snapchat",
    # WeChat
    "wechat": "WeChat",
    "weixin": "WeChat",
}


def read_metadata(file_path: str) -> MetadataResult:
    path = Path(file_path)
    result = MetadataResult(
        file_path=str(path),
        file_size_bytes=path.stat().st_size,
    )

    _read_ffprobe(file_path, result)
    _scan_for_ai_tags(result)
    _check_c2pa(file_path, result)
    _detect_platform_reencode(result)
    _detect_stripped_metadata(result)
    _check_duration(result)
    _fingerprint_resolution(result)
    _fingerprint_duration(result)

    return result


def _read_ffprobe(file_path: str, result: MetadataResult):
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        file_path
    ]
    # A transient ffprobe failure must not silently turn a tagged AI video
    # into "metadata stripped" (which reads as REAL) — retry once, and mark
    # the failure explicitly so downstream can distrust the emptiness.
    data = None
    for attempt in (1, 2):
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=8 * attempt)
            data = json.loads(output)
            break
        except Exception:
            continue
    if data is None:
        result.probe_failed = True
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


def _detect_platform_reencode(result: MetadataResult):
    all_text = " ".join([
        (result.software_tag or ""),
        (result.encoder_tag or ""),
        (result.creation_tool or ""),
        (result.comment_field or ""),
        " ".join(str(v) for v in result.all_tags.values()),
    ]).lower()

    for keyword, platform in PLATFORM_SIGNATURES.items():
        if keyword in all_text:
            result.platform_reencoded = True
            result.platform_name = platform
            return


def _detect_stripped_metadata(result: MetadataResult):
    """
    A video with absolutely no metadata tags is suspicious.
    Real cameras always write at least software/encoder/creation_time.
    A completely clean file suggests deliberate re-mux to hide AI origin.
    We only flag this if it's also NOT a known platform re-encode
    (platforms strip metadata too, but for different reasons).
    """
    has_any_tag = bool(
        result.software_tag or
        result.encoder_tag or
        result.creation_tool or
        result.creation_date or
        result.all_tags
    )
    if not has_any_tag and not result.platform_reencoded and not result.probe_failed:
        # probe_failed means we couldn't LOOK — absence of tags is then not evidence
        result.metadata_is_stripped = True


def _check_duration(result: MetadataResult):
    if result.duration_seconds is not None and result.duration_seconds < 2.0:
        result.too_short_for_analysis = True


def _check_c2pa(file_path: str, result: MetadataResult):
    """
    C2PA (Content Credentials) + binary AI-tool watermark detection.

    Two layers:
      1. Cryptographic C2PA verification via the official library — validates the
         manifest signature and reads digitalSourceType. Only this can set
         c2pa_is_ai (real proof of AI generation).
      2. Byte scan for the C2PA UUID box (presence signal) and for binary AI-tool
         watermarks embedded in the bitstream (Sora/Runway/Kling/...). A raw
         'c2pa.ai' string is treated as *presence only*, never as proof — anyone
         can embed that string.
    """
    # ── Layer 1: real cryptographic verification ─────────────────────────────
    try:
        from analyzer.c2pa_verifier import read_c2pa
        c2pa = read_c2pa(file_path)
        if c2pa.present:
            result.has_c2pa = True
            result.c2pa_verified = c2pa.signature_valid
            result.c2pa_is_ai = c2pa.is_ai
            result.c2pa_digital_source_type = c2pa.digital_source_type
            result.c2pa_claim_generator = c2pa.claim_generator
    except Exception:
        pass

    C2PA_UUID = b'\xd8\xfe\xc3\xd6\x1b\x0e\x48\x3c\x92\x97\x58\x28\x87\x7e\xc4\x81'
    CHUNK = 65536  # 64KB per read
    MAX_SCAN = 5 * 1024 * 1024  # scan up to 5MB

    # Binary signatures — AI tool watermarks embedded in the bitstream.
    # These survive even after metadata stripping because they're in the video data itself.
    BINARY_SIGS: list[tuple[bytes, str]] = [
        # OpenAI Sora
        (b'openai-sora',       "OpenAI Sora"),
        (b'sora_watermark',    "OpenAI Sora"),
        (b'openai.com/sora',   "OpenAI Sora"),
        (b'x-openai-sora',     "OpenAI Sora"),
        # Runway
        (b'runway_watermark',  "Runway"),
        (b'runwayml.com',      "Runway"),
        (b'runway-gen',        "Runway"),
        (b'gen3alpha',         "Runway Gen-3"),
        # Pika Labs
        (b'pika_watermark',    "Pika Labs"),
        (b'pika.art',          "Pika Labs"),
        (b'pikalabs',          "Pika Labs"),
        # Kling / Kuaishou
        (b'kling_watermark',   "Kuaishou Kling"),
        (b'kuaishou.com',      "Kuaishou Kling"),
        (b'klingai.com',       "Kuaishou Kling"),
        (b'kwai-kolors',       "Kuaishou Kling"),
        # Luma AI
        (b'luma_watermark',    "Luma AI"),
        (b'lumalabs.ai',       "Luma AI"),
        (b'luma-dream',        "Luma Dream Machine"),
        # MiniMax / Hailuo
        (b'hailuo.video',      "MiniMax Hailuo"),
        (b'minimax.com',       "MiniMax"),
        (b'minimax-video',     "MiniMax"),
        # HeyGen
        (b'heygen.com',        "HeyGen"),
        (b'HeyGen',            "HeyGen"),
        (b'heygen',            "HeyGen"),
        # Synthesia
        (b'synthesia',         "Synthesia"),
        (b'Synthesia',         "Synthesia"),
        (b'synthesia.io',      "Synthesia"),
        # D-ID
        (b'd-id.com',          "D-ID"),
        (b'did-video',         "D-ID"),
        # Creatify / InVideo
        (b'creatify',          "Creatify"),
        (b'invideo.io',        "InVideo AI"),
        # Google Veo
        (b'google-veo',        "Google Veo"),
        (b'deepmind-veo',      "Google Veo"),
        # Stability AI
        (b'stability.ai',      "Stability AI SVD"),
        (b'stable-video',      "Stability AI SVD"),
        # ByteDance / Seaweed
        (b'seaweed-video',     "ByteDance Seaweed"),
        (b'bytedance-gen',     "ByteDance Seaweed"),
        # Generic C2PA AI markers
        (b'c2pa.ai',           None),
        (b'ai.generated',      None),
    ]

    # IPTC DigitalSourceType — the open, standardized way to declare how media
    # was produced (http://cv.iptc.org/newscodes/digitalsourcetype/...). Adobe,
    # LinkedIn, Microsoft, TikTok and many AI tools write these tokens into XMP.
    # AI-declaring tokens (case-sensitive URI leaf names):
    IPTC_AI_TOKENS: list[tuple[bytes, str]] = [
        (b'trainedAlgorithmicMedia',              "trainedAlgorithmicMedia"),
        (b'compositeWithTrainedAlgorithmicMedia', "compositeWithTrainedAlgorithmicMedia"),
        (b'algorithmicMedia',                     "algorithmicMedia"),
        (b'compositeSynthetic',                   "compositeSynthetic"),
    ]
    # The symmetric real-origin leaves — an explicit "this was captured by a
    # camera" declaration. Reinforces a REAL verdict and lowers false positives.
    IPTC_CAPTURE_TOKENS: list[bytes] = [
        b'digitalCapture', b'negativeFilm', b'positiveFilm',
    ]

    # Overlap successive chunks by the longest signature so a marker split across
    # a 64KB boundary is still found.
    longest = max((len(s) for s, _ in BINARY_SIGS + IPTC_AI_TOKENS), default=0)
    longest = max([longest, len(C2PA_UUID)] + [len(s) for s in IPTC_CAPTURE_TOKENS])
    try:
        scanned = 0
        tail = b""
        with open(file_path, "rb") as f:
            while scanned < MAX_SCAN:
                block = f.read(CHUNK)
                if not block:
                    break
                scanned += len(block)
                chunk = tail + block

                if C2PA_UUID in chunk:
                    result.has_c2pa = True
                if b'c2pa.ai' in chunk:
                    # Presence only — a raw string is not cryptographic proof.
                    # c2pa_is_ai is set exclusively by Layer 1 verification above.
                    result.has_c2pa = True

                for sig, tool_name in BINARY_SIGS:
                    if sig in chunk and not result.ai_tool_detected:
                        result.ai_tool_detected = tool_name

                if not result.synthetic_media_marker:
                    for token, name in IPTC_AI_TOKENS:
                        if token in chunk:
                            result.synthetic_media_marker = True
                            result.iptc_digital_source_type = name
                            break
                if not result.capture_origin_marker:
                    for token in IPTC_CAPTURE_TOKENS:
                        if token in chunk:
                            result.capture_origin_marker = True
                            break

                tail = chunk[-longest:] if longest else b""
    except Exception:
        pass


def _fingerprint_resolution(result: MetadataResult):
    """
    Match video dimensions against known AI tool native resolutions.
    These survive platform re-encoding because resolution is preserved.
    """
    if not result.width or not result.height:
        return
    key = (result.width, result.height)
    match = AI_NATIVE_RESOLUTIONS.get(key)
    if match:
        result.resolution_ai_tool, result.resolution_ai_confidence = match


def _fingerprint_duration(result: MetadataResult):
    """
    Check if duration matches AI generation presets (e.g. exactly 5.0s, 10.0s).
    Real camera recordings almost never end at these exact millisecond values.
    """
    if not result.duration_seconds:
        return
    d = result.duration_seconds
    for preset in AI_TYPICAL_DURATIONS:
        if abs(d - preset) <= DURATION_TOL:
            result.duration_is_ai_typical = True
            return

"""
Label-safe classification of a video file's class from its path inside a
Hugging Face detection benchmark.

Multi-generator detection benchmarks (GenVideo, GenVidBench, AEGIS, CoCoVideo…)
pack BOTH real and AI videos into one repo, split by folder — e.g.
    fake/kling/clip001.mp4      -> AI
    real/vript/clip042.mp4      -> real
So we must NOT label a whole repo one way. This maps a single file's path to
its class using strong, well-known tokens, and returns None (SKIP) whenever the
path is ambiguous or unrecognized. Skipping the uncertain ones is the whole
point: it is always safe to collect fewer samples, never safe to mislabel one.
"""
import re

# Known AI video generators + explicit "generated" markers. A path containing
# any of these (and no real-marker) is AI.
_AI_TOKENS = [
    "sora", "kling", "pika", "veo", "runway", "gen-2", "gen2", "gen-3", "gen3",
    "luma", "dreammachine", "dream-machine", "cogvideo", "cogvideox",
    "modelscope", "model-scope", "videocrafter", "video-crafter", "lavie",
    "latte", "hotshot", "zeroscope", "animatediff", "stable-video",
    "stablevideo", "stable-video-diffusion", "svd", "text2video", "text-to-video",
    "t2v", "opensora", "open-sora", "seine", "show-1", "i2vgen", "dynamicrafter",
    "easyanimate", "allegro", "mochi", "hunyuan", "wanx", "ltx", "seedance",
    "hailuo", "vidu", "genmo", "moonvalley", "cogvideox-5b", "opensora-plan",
    "generated", "synthetic", "aigc", "genvideo", "gen_video",
]
# Explicit real/source markers. A path with any of these (and no AI-marker) is real.
_REAL_TOKENS = [
    "vript", "msrvtt", "msr-vtt", "msr_vtt", "kinetics", "webvid", "panda-70m",
    "panda70m", "pexels", "pixabay", "ground-truth", "groundtruth",
    "pristine", "davis", "youtube-real", "camera-captured", "natural-video",
]
# Folder-boundary markers (matched with separators so "areal" ≠ "real").
_AI_DIR = ["fake", "ai", "generated", "synthetic"]
_REAL_DIR = ["real", "gt", "pristine", "authentic"]

_SEP = r"[\\/_\-.]"


def _has_token(low: str, tokens) -> bool:
    return any(tok in low for tok in tokens)


def _has_dir(low: str, dirs) -> bool:
    # match a token delimited by path/word separators or string ends
    return any(re.search(rf"(^|{_SEP}){re.escape(d)}({_SEP}|$)", low) for d in dirs)


def classify(path: str):
    """Return 'ai', 'real', or None (skip if ambiguous/unknown)."""
    low = path.lower()
    ai = _has_token(low, _AI_TOKENS) or _has_dir(low, _AI_DIR)
    real = _has_token(low, _REAL_TOKENS) or _has_dir(low, _REAL_DIR)
    if ai and not real:
        return "ai"
    if real and not ai:
        return "real"
    return None  # both or neither → never guess

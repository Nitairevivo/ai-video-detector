"""
Platform AI-disclosure flags — YouTube, Instagram, Facebook.

Platforms transcode uploads (destroying file metadata / C2PA manifests),
but their own AI-disclosure label lives in the page/API JSON and survives.
This is the same idea as tiktok_resolver's AIGC extraction, generalized.

Patterns are anchored to JSON string boundaries ("key":"Exact label") so a
video *about* AI labels (title/comments mentioning them) doesn't match.
"""
import re
import gzip
import json
import urllib.request
from dataclasses import dataclass
from typing import Optional

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# YouTube innertube WEB client — public key baked into youtube.com's JS
# (not a secret; identical for every anonymous web visitor).
_YT_INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
_YT_CLIENT = {"clientName": "WEB", "clientVersion": "2.20240710.01.00"}
_YT_ID_RE = re.compile(
    r"(?:v=|/shorts/|/embed/|youtu\.be/|/live/)([A-Za-z0-9_-]{11})"
)

# ── Per-platform markers ──────────────────────────────────────────────────────
# Each entry: (compiled regex, human-readable info). English labels are enough
# because we request Accept-Language: en-US.

_YOUTUBE_MARKERS = [
    # Description badge: "How this content was made — Altered or synthetic content"
    (re.compile(r'"(?:label|title|text|simpleText|content)"\s*:\s*"Altered or synthetic content"'),
     "YouTube 'Altered or synthetic content' disclosure"),
    (re.compile(r'"Sound or visuals were significantly edited or digitally generated'),
     "YouTube synthetic-media disclosure text"),
    # Current (2026) format: an instantiated howThisWasMadeSectionViewModel object.
    # Must match `:{` — the bare name also appears in a renderer-registry list on
    # every watch page, which must NOT count as a flag.
    (re.compile(r'"howThisWasMadeSectionViewModel"\s*:\s*\{'),
     "YouTube 'How this was made' disclosure section"),
    (re.compile(r'"Sounds? or visuals were (?:altered or (?:fully |digitally )?generated|significantly edited)'),
     "YouTube altered/generated disclosure text"),
]

_META_MARKERS = [
    # Structured field set when Meta detects/user discloses GenAI content
    (re.compile(r'"gen_ai_detection_method"\s*:\s*\{[^{}]*"detection_method"\s*:\s*"[a-z]'),
     "Meta gen_ai_detection_method field"),
    (re.compile(r'"(?:label|text|title)"\s*:\s*"(?:AI info|Made with AI)"'),
     "Meta 'AI info' label"),
    (re.compile(r'"is_gen_ai"\s*:\s*true'),
     "Meta is_gen_ai flag"),
]


@dataclass
class PlatformFlag:
    platform: str          # "youtube" | "instagram" | "facebook" | "unknown"
    checked: bool = False  # page fetched and scanned
    flagged: bool = False  # platform marks this video as AI
    info: str = ""


def _fetch_page(url: str, timeout: int = 12) -> Optional[str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": DESKTOP_UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(6 * 1024 * 1024)
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return data.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _youtube_video_id(url: str) -> Optional[str]:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def _fetch_innertube_next(video_id: str, timeout: int = 12) -> Optional[str]:
    """
    YouTube innertube /next — the structured data API behind the watch page.
    More reliable than HTML scraping: the description panel (where the
    'Altered or synthetic content' disclosure lives) is server-rendered here
    rather than injected client-side.
    """
    body = json.dumps({
        "context": {"client": _YT_CLIENT},
        "videoId": video_id,
    }).encode()
    req = urllib.request.Request(
        f"https://www.youtube.com/youtubei/v1/next?key={_YT_INNERTUBE_KEY}&prettyPrint=false",
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": DESKTOP_UA,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(8 * 1024 * 1024).decode("utf-8", errors="ignore")
    except Exception:
        return None


def _platform_of(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "instagram.com" in u:
        return "instagram"
    if "facebook.com" in u or "fb.watch" in u:
        return "facebook"
    return "unknown"


def _scan_markers(text: str, markers) -> Optional[str]:
    """Return the info string of the first matching marker, else None."""
    for pattern, info in markers:
        if pattern.search(text):
            return info
    return None


def check_platform_ai_flag(url: str) -> PlatformFlag:
    """
    Fetch the platform's data for the video and scan for its own AI-disclosure
    label. flagged=True is a definitive signal (the platform itself labeled it).
    checked=False means no source could be fetched — not a negative result.

    YouTube uses two sources: the watch-page HTML *and* the innertube /next API
    (the disclosure may be server-rendered in one but not the other).
    """
    platform = _platform_of(url)
    flag = PlatformFlag(platform=platform)
    if platform == "unknown":
        return flag

    if platform == "youtube":
        markers = _YOUTUBE_MARKERS
        sources = []
        html = _fetch_page(url)
        if html is not None:
            sources.append(("html", html))
        vid = _youtube_video_id(url)
        if vid:
            nxt = _fetch_innertube_next(vid)
            if nxt is not None:
                sources.append(("innertube", nxt))
        if not sources:
            return flag
        flag.checked = True
        for src_name, text in sources:
            info = _scan_markers(text, markers)
            if info:
                flag.flagged = True
                flag.info = f"{info} (via {src_name})"
                return flag
        return flag

    # Instagram / Facebook — HTML only
    html = _fetch_page(url)
    if html is None:
        return flag
    flag.checked = True
    info = _scan_markers(html, _META_MARKERS)
    if info:
        flag.flagged = True
        flag.info = info
    return flag

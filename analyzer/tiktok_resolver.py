"""
TikTok video resolver — extracts CDN video URL and AIGC labels.

Strategies (in order of reliability):
1. oEmbed API (fastest, rarely blocked)
2. Embed page /embed/v2/<ID> (lightweight, less blocked)
3. App API endpoint (mobile JSON, no HTML parsing)
4. Full page HTML with multiple UA rotations
5. SIGI_STATE / __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON blobs
6. Regex CDN pattern fallback
"""
import re
import json
import time
import urllib.request
import urllib.parse
import random
from typing import Optional, Tuple

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.2 Mobile/15E148 Safari/604.1"
)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Multiple UAs to rotate through when one gets blocked
USER_AGENTS = [
    MOBILE_UA,
    DESKTOP_UA,
    (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.6367.82 Mobile Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.2.1 Safari/605.1.15"
    ),
]

CDN_PATTERNS = [
    r'(https://v[0-9]+-webapp\.tiktok\.com[^"\'\\]+\.mp4[^"\'\\]*)',
    r'(https://[^"\'\\]*tiktokcdn[^"\'\\]+\.mp4[^"\'\\]*)',
    r'(https://[^"\'\\]*muscdn[^"\'\\]+\.mp4[^"\'\\]*)',
    r'"downloadAddr":"([^"]+)"',
    r'"playAddr":"([^"]+)"',
    r'"url":"(https://[^"]+\.mp4[^"]*)"',
    r'"video_url":"(https://[^"]+)"',
]

# All known TikTok AIGC field names across API versions
AIGC_PATTERNS = [
    r'"aigc_label[s]?":\s*\[([^\]]*)\]',
    r'"aigcContent":\s*\{([^}]*)\}',
    r'"is_ai_generated":\s*(true|1)',
    r'"aigc_disclosure_type":\s*([1-9]\d*)',
    r'"ai_generated":\s*(true|1)',
    r'"aigcLabelType":\s*([1-9]\d*)',
    r'"AILabel":\s*"([^"]+)"',
    r'"aigcType":\s*([1-9]\d*)',
    r'"aiType":\s*([1-9]\d*)',
    r'"aigc_info":\s*\{[^}]*"aigc_method":\s*([1-9]\d*)',
    r'"created_by_ai":\s*(true|1)',
    r'"isAigc":\s*(true|1)',
    r'"is_aigc":\s*(true|1)',
    r'"aigcFlag":\s*([1-9]\d*)',
]

AIGC_JSON_KEYS = [
    "aigc_label", "aigcContent", "is_ai_generated", "aigc_disclosure_type",
    "ai_generated", "aigcLabelType", "AILabel", "aigcType", "aiType",
    "created_by_ai", "isAigc", "is_aigc", "aigcFlag", "aigc_info",
    "aigc_method",
]


def _extract_video_id(url: str) -> Optional[str]:
    """Extract numeric video ID from any TikTok URL format."""
    m = re.search(r'/video/(\d{10,20})', url)
    if m:
        return m.group(1)
    m = re.search(r'/(\d{15,20})(?:\?|$|/)', url)
    if m:
        return m.group(1)
    return None


def _fetch(url: str, ua: str = MOBILE_UA, timeout: int = 12,
           referer: str = "https://www.tiktok.com/") -> Optional[str]:
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                import gzip
                try:
                    return gzip.decompress(raw).decode("utf-8")
                except Exception:
                    return raw.decode("utf-8", errors="ignore")
    except Exception:
        return None


def _is_aigc_value(val) -> bool:
    """Return True if a JSON value indicates AI-generated content."""
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes") or (val.isdigit() and int(val) > 0)
    if isinstance(val, list) and len(val) > 0:
        return True  # non-empty aigc_labels list means AI
    if isinstance(val, dict) and val:
        return True
    return False


def _scan_html_for_aigc(html: str) -> Tuple[bool, str]:
    """Scan raw HTML for any AIGC indicator."""
    for pat in AIGC_PATTERNS:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return True, f"AIGC pattern matched: {pat[:40]}"
    return False, ""


def _find_in_nested(obj, keys: list, depth: int = 0) -> Optional[object]:
    """Recursively search nested dict/list for any of the given keys."""
    if depth > 15:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                return v
            result = _find_in_nested(v, keys, depth + 1)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_in_nested(item, keys, depth + 1)
            if result is not None:
                return result
    return None


def _extract_json_blob(html: str, key: str) -> Optional[dict]:
    patterns = [
        rf'<script id="{key}"[^>]*>(.*?)</script>',
        rf'window\["{key}"\]\s*=\s*({{.*?}});',
        rf'var {key}\s*=\s*({{.*?}});',
        rf'"{key}":\s*({{.*?}})\s*[,}}]',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None


# ─── Strategy 1: oEmbed API ────────────────────────────────────────────────────

def _try_oembed(url: str) -> Tuple[bool, str]:
    """TikTok's oEmbed endpoint — fast, no IP blocking, returns JSON."""
    try:
        oembed_url = f"https://www.tiktok.com/oembed?url={urllib.parse.quote(url)}"
        html = _fetch(oembed_url, ua=MOBILE_UA, timeout=8, referer="https://www.tiktok.com/")
        if not html:
            return False, ""
        try:
            data = json.loads(html)
        except Exception:
            return False, ""
        text = json.dumps(data).lower()
        if any(x in text for x in ["aigc", "ai_generated", "ai generated", "ai-generated",
                                    "created by ai", "isai", "aicontent"]):
            return True, f"oEmbed AIGC field detected"
        for key in AIGC_JSON_KEYS:
            val = data.get(key)
            if val is not None and _is_aigc_value(val):
                return True, f"oEmbed {key}={val}"
    except Exception:
        pass
    return False, ""


# ─── Strategy 2: Embed page ────────────────────────────────────────────────────

def _try_embed_page(video_id: str) -> Tuple[bool, str]:
    """TikTok embed iframe — lighter page, often less bot-challenged."""
    if not video_id:
        return False, ""
    url = f"https://www.tiktok.com/embed/v2/{video_id}"
    for ua in [MOBILE_UA, DESKTOP_UA]:
        html = _fetch(url, ua=ua, timeout=10, referer="https://www.tiktok.com/")
        if html and len(html) > 500:
            is_aigc, info = _scan_html_for_aigc(html)
            if is_aigc:
                return True, f"Embed page: {info}"
            # Parse any JSON in the embed page
            for blob_key in ["__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE", "__NEXT_DATA__"]:
                blob = _extract_json_blob(html, blob_key)
                if blob:
                    val = _find_in_nested(blob, AIGC_JSON_KEYS)
                    if val is not None and _is_aigc_value(val):
                        return True, f"Embed page JSON blob: aigc detected"
    return False, ""


# ─── Strategy 3: TikTok app API endpoint ──────────────────────────────────────

def _try_app_api(video_id: str) -> Tuple[bool, Optional[str], str]:
    """
    Try TikTok's mobile app API endpoint.
    Returns (is_aigc, cdn_url, info).
    """
    if not video_id:
        return False, None, ""

    endpoints = [
        f"https://api16-normal-c-useast1a.tiktokv.com/aweme/v1/feed/?aweme_id={video_id}&count=1",
        f"https://api22-normal-c-alisg.tiktokv.com/aweme/v1/feed/?aweme_id={video_id}&count=1",
    ]
    for ep in endpoints:
        try:
            headers = {
                "User-Agent": "TikTok 26.2.0 rv:262018 (iPhone; iOS 14.4.2; en_US) Cronet",
                "Accept": "application/json",
            }
            req = urllib.request.Request(ep, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())

            items = data.get("aweme_list", [])
            if not items:
                continue
            item = items[0]

            # AIGC check
            is_aigc = False
            for key in AIGC_JSON_KEYS:
                val = _find_in_nested(item, [key])
                if val is not None and _is_aigc_value(val):
                    is_aigc = True
                    break

            # CDN URL
            cdn_url = None
            video = item.get("video", {})
            for url_key in ["play_addr", "download_addr"]:
                addr = video.get(url_key, {})
                urls = addr.get("url_list", [])
                if urls:
                    cdn_url = urls[0]
                    break

            return is_aigc, cdn_url, "App API: success"
        except Exception:
            continue
    return False, None, ""


# ─── Strategy 4: Full page scrape with UA rotation ────────────────────────────

def _try_full_page(url: str) -> Tuple[bool, Optional[str], str]:
    """Fetch full TikTok page with UA rotation. Returns (is_aigc, cdn_url, info)."""
    for ua in USER_AGENTS:
        html = _fetch(url, ua=ua, timeout=15)
        if not html or len(html) < 2000:
            time.sleep(0.3)
            continue

        # Check for bot challenge
        if any(x in html for x in ["captcha", "verifyPage", "robot", "challenge"]):
            continue

        is_aigc = False

        # Pattern scan
        aigc_found, aigc_info = _scan_html_for_aigc(html)
        if aigc_found:
            is_aigc = True

        # JSON blob parsing
        cdn_url = None
        for blob_key in ["__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE", "__NEXT_DATA__"]:
            blob = _extract_json_blob(html, blob_key)
            if not blob:
                continue
            # AIGC
            if not is_aigc:
                val = _find_in_nested(blob, AIGC_JSON_KEYS)
                if val is not None and _is_aigc_value(val):
                    is_aigc = True
            # CDN URL
            if not cdn_url:
                for url_key in ["downloadAddr", "playAddr", "video_url", "url"]:
                    val = _find_in_nested(blob, [url_key])
                    if isinstance(val, str) and "tiktok" in val and ".mp4" in val:
                        cdn_url = val.replace("\\u0026", "&").replace("\\/", "/")
                        break
                    if isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                u = (_find_in_nested(item, ["PlayAddr"]) or {})
                                if isinstance(u, dict):
                                    urls = u.get("UrlList", [])
                                    if urls:
                                        cdn_url = urls[0]
                                        break

        # Regex CDN fallback
        if not cdn_url:
            for pat in CDN_PATTERNS:
                m = re.search(pat, html)
                if m:
                    raw = m.group(1).replace("\\u0026", "&").replace("\\/", "/")
                    if raw.startswith("http"):
                        cdn_url = raw
                        break

        if cdn_url or is_aigc:
            return is_aigc, cdn_url, f"Full page (UA={ua[:20]})"

    return False, None, "All page strategies failed"


# ─── Public API ───────────────────────────────────────────────────────────────

def resolve_tiktok(share_url: str) -> Tuple[Optional[str], bool, str]:
    """
    Resolve a TikTok URL.
    Returns (cdn_video_url_or_None, is_aigc, aigc_info).

    Tries 4 strategies in order of speed/reliability.
    """
    # Follow short-link redirects
    try:
        req = urllib.request.Request(share_url, headers={"User-Agent": MOBILE_UA})
        req.method = "HEAD"
        with urllib.request.urlopen(req, timeout=8) as r:
            final_url = r.url
    except Exception:
        final_url = share_url

    video_id = _extract_video_id(final_url) or _extract_video_id(share_url)

    # Strategy 1: oEmbed (fastest, least blocked)
    is_aigc, info = _try_oembed(final_url)
    if is_aigc:
        return None, True, info

    # Strategy 2: Embed page (lightweight)
    if video_id:
        is_aigc, info = _try_embed_page(video_id)
        if is_aigc:
            return None, True, info

    # Strategy 3: App API (gets CDN URL + AIGC in one call)
    if video_id:
        is_aigc, cdn_url, info = _try_app_api(video_id)
        if is_aigc:
            return cdn_url, True, f"App API: AIGC confirmed"
        if cdn_url:
            return cdn_url, False, info

    # Strategy 4: Full page with UA rotation
    is_aigc, cdn_url, info = _try_full_page(final_url)
    return cdn_url, is_aigc, info


def download_tiktok_video(share_url: str, output_path: str, max_mb: int = 30) -> Tuple[bool, bool, str]:
    """
    Download a TikTok video to output_path.
    Returns (success, is_aigc, aigc_info).
    """
    cdn_url, is_aigc, aigc_info = resolve_tiktok(share_url)

    if not cdn_url:
        return False, is_aigc, aigc_info

    try:
        limit = max_mb * 1024 * 1024
        headers = {
            "User-Agent": MOBILE_UA,
            "Referer": "https://www.tiktok.com/",
            "Range": f"bytes=0-{limit - 1}",
        }
        req = urllib.request.Request(cdn_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()

        if len(data) < 10000:
            return False, is_aigc, aigc_info

        with open(output_path, "wb") as f:
            f.write(data)

        return True, is_aigc, aigc_info
    except Exception as e:
        return False, is_aigc, f"{aigc_info} | download error: {e}"

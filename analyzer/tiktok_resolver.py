"""
TikTok video resolver — extracts CDN video URL and AIGC labels
from the TikTok page HTML using the phone's residential IP.

Strategies:
1. Parse __UNIVERSAL_DATA_FOR_REHYDRATION__ JSON blob
2. Parse SIGI_STATE JSON blob
3. Regex search for video CDN patterns
4. Extract aigc_label / is_ai_generated fields
"""
import re
import json
import urllib.request
import urllib.parse
from typing import Optional, Tuple

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.2 Mobile/15E148 Safari/604.1"
)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CDN_PATTERNS = [
    r'(https://v[0-9]+-webapp\.tiktok\.com[^"\'\\]+\.mp4[^"\'\\]*)',
    r'(https://[^"\'\\]*tiktokcdn[^"\'\\]+\.mp4[^"\'\\]*)',
    r'(https://[^"\'\\]*muscdn[^"\'\\]+\.mp4[^"\'\\]*)',
    r'"downloadAddr":"([^"]+)"',
    r'"playAddr":"([^"]+)"',
    r'"url":"(https://[^"]+\.mp4[^"]*)"',
    r'"video_url":"(https://[^"]+)"',
]

AIGC_PATTERNS = [
    r'"aigc_label[s]?":\s*\[([^\]]*)\]',
    r'"aigcContent":\s*\{([^}]*)\}',
    r'"is_ai_generated":\s*(true|false|1|0)',
    r'"aigc_disclosure_type":\s*(\d+)',
    r'"ai_generated":\s*(true|false)',
    r'"aigcLabelType":\s*(\d+)',
    r'"AILabel":\s*"([^"]+)"',
]


def _fetch_page(url: str, mobile: bool = False) -> Optional[str]:
    headers = {
        "User-Agent": MOBILE_UA if mobile else DESKTOP_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
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


def _extract_json_blob(html: str, key: str) -> Optional[dict]:
    """Extract and parse a JSON blob embedded in page HTML."""
    patterns = [
        rf'<script id="{key}"[^>]*>(.*?)</script>',
        rf'window\["{key}"\]\s*=\s*({{.*?}});',
        rf'var {key}\s*=\s*({{.*?}});',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
    return None


def _find_in_nested(obj, keys: list) -> Optional[object]:
    """Recursively search nested dict/list for any of the given keys."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                return v
            result = _find_in_nested(v, keys)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_in_nested(item, keys)
            if result is not None:
                return result
    return None


def resolve_tiktok(share_url: str) -> Tuple[Optional[str], bool, str]:
    """
    Resolve a TikTok share/video URL.
    Returns (cdn_video_url, is_aigc_labeled, aigc_info).
    """
    # Follow redirects (vm.tiktok.com short links)
    try:
        req = urllib.request.Request(share_url, headers={"User-Agent": MOBILE_UA})
        req.method = "HEAD"
        with urllib.request.urlopen(req, timeout=10) as r:
            final_url = r.url
    except Exception:
        final_url = share_url

    # Try desktop page first (more data in JSON blobs)
    html = _fetch_page(final_url, mobile=False)
    if not html or len(html) < 1000:
        html = _fetch_page(final_url, mobile=True)
    if not html:
        return None, False, "Page fetch failed"

    # ── Check AIGC labels ──────────────────────────────────────────────────────
    is_aigc = False
    aigc_info = ""

    for pat in AIGC_PATTERNS:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            if val in ("true", "1") or (val.isdigit() and int(val) > 0):
                is_aigc = True
                aigc_info = f"TikTok AIGC label detected (pattern: {pat[:30]})"
                break
            if val not in ("false", "0", ""):
                aigc_info = f"AIGC field: {val}"

    # Try JSON blobs for richer data
    for blob_key in ["__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE", "__NEXT_DATA__"]:
        blob = _extract_json_blob(html, blob_key)
        if blob:
            # Search for AIGC flags
            for aigc_key in ["aigc_label", "aigcContent", "is_ai_generated", "ai_generated", "aigcLabelType"]:
                val = _find_in_nested(blob, [aigc_key])
                if val is not None:
                    if val in (True, 1, "1", "true") or (isinstance(val, (int, float)) and val > 0):
                        is_aigc = True
                        aigc_info = f"TikTok AIGC: {aigc_key}={val}"
                    break

    # ── Extract video CDN URL ──────────────────────────────────────────────────
    cdn_url = None

    # Try JSON blobs first
    for blob_key in ["__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE", "__NEXT_DATA__"]:
        blob = _extract_json_blob(html, blob_key)
        if not blob:
            continue
        for url_key in ["downloadAddr", "playAddr", "video_url", "url", "bitrateInfo"]:
            val = _find_in_nested(blob, [url_key])
            if isinstance(val, str) and "tiktok" in val and ".mp4" in val:
                cdn_url = val.replace("\\u0026", "&").replace("\\/", "/")
                break
            if isinstance(val, list) and val:
                # bitrateInfo is a list of quality options
                for item in val:
                    if isinstance(item, dict):
                        u = item.get("PlayAddr", {}).get("UrlList", [None])[0]
                        if u and "tiktok" in u:
                            cdn_url = u
                            break
        if cdn_url:
            break

    # Regex fallback
    if not cdn_url:
        for pat in CDN_PATTERNS:
            m = re.search(pat, html)
            if m:
                url_raw = m.group(1).replace("\\u0026", "&").replace("\\/", "/")
                if url_raw.startswith("http"):
                    cdn_url = url_raw
                    break

    return cdn_url, is_aigc, aigc_info


def download_tiktok_video(share_url: str, output_path: str, max_mb: int = 30) -> Tuple[bool, bool, str]:
    """
    Download a TikTok video to output_path.
    Returns (success, is_aigc, aigc_info).
    """
    cdn_url, is_aigc, aigc_info = resolve_tiktok(share_url)

    if not cdn_url:
        return False, is_aigc, aigc_info

    try:
        headers = {
            "User-Agent": MOBILE_UA,
            "Referer": "https://www.tiktok.com/",
            "Range": f"bytes=0-{max_mb * 1024 * 1024 - 1}",
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

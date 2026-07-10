"""Tests for analyzer/platform_flags.py — pattern matching only, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyzer.platform_flags import (
    _YOUTUBE_MARKERS, _META_MARKERS, _TWITTER_MARKERS, _platform_of,
    _youtube_video_id, _scan_markers, _TW_ID_RE,
)


def _scan(markers, html):
    return any(p.search(html) for p, _ in markers)


def test_youtube_badge_matches():
    html = '{"metadataBadgeRenderer":{"label":"Altered or synthetic content","icon":{}}}'
    assert _scan(_YOUTUBE_MARKERS, html)


def test_youtube_disclosure_text_matches():
    html = '{"text":"Sound or visuals were significantly edited or digitally generated."}'
    assert _scan(_YOUTUBE_MARKERS, html)


def test_youtube_video_about_the_label_does_not_match():
    # A video whose title/comments merely mention the label must not flag
    html = '{"title":"YouTube Altered or synthetic content label explained!","comment":"what is Made with AI?"}'
    assert not _scan(_YOUTUBE_MARKERS, html)


def test_meta_detection_method_matches():
    html = '{"gen_ai_detection_method":{"detection_method":"user_disclosure"}}'
    assert _scan(_META_MARKERS, html)


def test_meta_ai_info_label_matches():
    html = '{"label":"AI info"}'
    assert _scan(_META_MARKERS, html)


def test_meta_caption_mentioning_ai_does_not_match():
    html = '{"caption":"Made with AI tools, check my AI info page","gen_ai_detection_method":null}'
    assert not _scan(_META_MARKERS, html)


def test_youtube_video_id_extraction():
    assert _youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _youtube_video_id("https://youtu.be/dQw4w9WgXcQ?si=abc") == "dQw4w9WgXcQ"
    assert _youtube_video_id("https://www.youtube.com/shorts/abc12345678") == "abc12345678"
    assert _youtube_video_id("https://www.youtube.com/embed/abcdef_-123") == "abcdef_-123"
    assert _youtube_video_id("https://www.youtube.com/live/ZYXwvut12_3") == "ZYXwvut12_3"
    assert _youtube_video_id("https://www.youtube.com/feed/subscriptions") is None


def test_scan_markers_matches_innertube_shape():
    # innertube /next carries the disclosure text in a runs/text node
    innertube = '{"videoSecondaryInfoRenderer":{"metadataRowContainer":{"rows":[{"text":"Altered or synthetic content"}]}}}'
    assert _scan_markers(innertube, _YOUTUBE_MARKERS) is not None
    # a plain video has no such marker
    assert _scan_markers('{"videoSecondaryInfoRenderer":{"title":"My vlog"}}', _YOUTUBE_MARKERS) is None


def test_platform_routing():
    assert _platform_of("https://youtu.be/abc") == "youtube"
    assert _platform_of("https://www.youtube.com/shorts/xyz") == "youtube"
    assert _platform_of("https://www.instagram.com/reel/xyz/") == "instagram"
    assert _platform_of("https://fb.watch/abc/") == "facebook"
    assert _platform_of("https://x.com/user/status/123") == "twitter"
    assert _platform_of("https://twitter.com/user/status/123") == "twitter"
    assert _platform_of("https://example.com/video.mp4") == "unknown"


# ── X / Twitter ───────────────────────────────────────────────────────────────
def test_twitter_id_extraction():
    assert _TW_ID_RE.search("https://x.com/jack/status/1789012345678").group(1) == "1789012345678"
    assert _TW_ID_RE.search("https://twitter.com/a_b/status/42").group(1) == "42"
    assert _TW_ID_RE.search("https://x.com/jack") is None


def test_twitter_grok_attribution_flags():
    assert _scan_markers('{"source":"Grok Imagine","text":"a cat"}', _TWITTER_MARKERS) is not None


def test_twitter_made_with_ai_flags():
    assert _scan_markers('{"displayText":"Made with AI"}', _TWITTER_MARKERS) is not None
    assert _scan_markers('{"is_ai_generated":true}', _TWITTER_MARKERS) is not None


def test_twitter_tweet_merely_mentioning_ai_does_not_match():
    j = '{"text":"grok and Made with AI labels are interesting","source":"Twitter for iPhone"}'
    assert _scan_markers(j, _TWITTER_MARKERS) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok - {fn.__name__}")
    print(f"{len(fns)} tests passed")

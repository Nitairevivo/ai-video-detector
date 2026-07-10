"""
Regression tests for bugs found in the full-codebase sweep.
Each test pins a specific fix so the bug can't silently return.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── image: short brand tokens must not match inside real words ────────────────
def test_flux_reve_not_matched_in_ordinary_words():
    from analyzer.image_analyzer import _tool_from_text
    # "forever" contains "reve", "influx" contains "flux" — must NOT flag AI.
    assert _tool_from_text({"imagedescription": "best friends forever"}) is None
    assert _tool_from_text({"imagedescription": "there was an influx of tourists"}) is None
    assert _tool_from_text({"software": "reverie photo editor"}) is None


def test_real_tool_tags_still_detected_after_boundary_fix():
    from analyzer.image_analyzer import _tool_from_text
    assert _tool_from_text({"software": "Adobe Firefly"}) == "Adobe Firefly"
    assert _tool_from_text({"imagedescription": "generated with flux"}) == "Flux (Black Forest Labs)"
    # token adjacent to punctuation/space still matches
    assert _tool_from_text({"software": "Midjourney v6"}) == "Midjourney"


def test_byte_scan_short_token_in_word_not_flagged(tmp_path):
    from analyzer.image_analyzer import _byte_scan
    p = tmp_path / "caption.jpg"
    # 'reve' sits inside the printable word 'forever' — printable region passes,
    # but the word-boundary guard must reject it.
    p.write_bytes(b"\xff\xd8\xff\xe0" + b"Comment: friends forever and always\x00" + b"\x00" * 20)
    assert _byte_scan(str(p))["ai_tool"] is None


# ── SSRF guard ────────────────────────────────────────────────────────────────
def test_ssrf_guard_blocks_internal_addresses():
    from api.server import _is_safe_public_url
    assert _is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False  # cloud metadata
    assert _is_safe_public_url("http://127.0.0.1:8080/") is False                    # loopback
    assert _is_safe_public_url("http://10.0.0.5/video.mp4") is False                 # private
    assert _is_safe_public_url("http://192.168.1.1/") is False                       # private
    assert _is_safe_public_url("ftp://8.8.8.8/x") is False                           # bad scheme
    assert _is_safe_public_url("not a url") is False


def test_ssrf_guard_allows_public_ip():
    from api.server import _is_safe_public_url
    assert _is_safe_public_url("https://8.8.8.8/video.mp4") is True


# ── billing: monthly quota resets across month boundary ───────────────────────
def test_quota_resets_when_billing_month_is_stale():
    from api.database import _row_to_key, _billing_month
    base = {
        "key_id": "k1", "email": "a@b.c", "tier": "free",
        "requests_this_month": 100, "requests_total": 500,
        "stripe_customer_id": None, "stripe_subscription_id": None,
        "created_at": "2026-01-01T00:00:00+00:00", "active": 1,
    }
    stale = dict(base, billing_month="2020-01")   # not the current month
    k = _row_to_key(stale)
    assert k.requests_this_month == 0        # effectively reset
    assert k.over_limit is False             # so the user is NOT locked out

    current = dict(base, billing_month=_billing_month())
    k2 = _row_to_key(current)
    assert k2.requests_this_month == 100     # current month counts normally
    assert k2.over_limit is True


# ── training: seed merge keeps source-less rows (T3) ──────────────────────────
def test_image_seed_merge_keeps_sourceless_rows(tmp_path, monkeypatch):
    import json
    import training.collect_images as ci
    main = [{"features": [0.0], "label": 0, "source": "acc1"}]
    seed = [
        {"features": [1.0], "label": 0, "source": "u1"},
        {"features": [2.0], "label": 0},           # no source — must be kept
        {"features": [3.0], "label": 0},           # no source — must be kept too
    ]
    dpath = tmp_path / "img.json"; spath = tmp_path / "seed.json"
    dpath.write_text(json.dumps(main)); spath.write_text(json.dumps(seed))
    monkeypatch.setattr(ci, "DATA", dpath)
    monkeypatch.setattr(ci, "USER_SEED", spath)
    merged = ci._load_all()
    assert len(merged) == 4   # 1 acc + u1 + 2 source-less (none dropped)

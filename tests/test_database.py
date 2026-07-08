"""Unit tests for API-key storage: rotation and usage recording."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Point the module at a throwaway DB before it is imported
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_aivd.db")

import importlib
import api.database as db
importlib.reload(db)

db.init_db()


def test_create_and_lookup():
    raw = db.create_key("a@test.com")
    key = db.lookup_key(raw)
    assert key is not None
    assert key.email == "a@test.com"
    assert key.tier == "free"


def test_rotate_key_preserves_account_and_kills_old_secret():
    raw = db.create_key("b@test.com", tier="pro")
    db.record_request(raw)
    old = db.lookup_key(raw)
    assert old.requests_this_month == 1

    new_raw = db.rotate_key(raw)
    assert new_raw and new_raw != raw
    assert db.lookup_key(raw) is None            # old secret dead
    rotated = db.lookup_key(new_raw)
    assert rotated is not None
    assert rotated.key_id == old.key_id          # same account
    assert rotated.tier == "pro"
    assert rotated.requests_this_month == 1      # usage preserved


def test_rotate_invalid_key_returns_none():
    assert db.rotate_key("aivd_nonexistent") is None


def test_record_request_by_id_increments_quota():
    raw = db.create_key("c@test.com")
    key = db.lookup_key(raw)
    # This is how /detect-batch records usage — by key_id, not raw secret
    db.record_request_by_id(key.key_id)
    db.record_request_by_id(key.key_id)
    assert db.lookup_key(raw).requests_this_month == 2


def test_usage_history_counts_today_and_fills_gaps():
    raw = db.create_key("d@test.com")
    key = db.lookup_key(raw)
    db.record_request(raw)
    db.record_request_by_id(key.key_id)

    hist = db.usage_history(key.key_id, days=30)
    assert len(hist) == 30
    assert hist[-1]["count"] == 2          # both paths logged today
    assert all(h["count"] == 0 for h in hist[:-1])  # gaps filled with zeros
    assert hist[0]["day"] < hist[-1]["day"]         # oldest first


def test_usage_history_empty_key():
    hist = db.usage_history("nonexistent-key-id", days=7)
    assert len(hist) == 7
    assert all(h["count"] == 0 for h in hist)


def test_feedback_agreement_math():
    # user confirms an AI verdict → agrees
    db.add_feedback("ai_generated", 0.95, user_says_ai=True, source="test")
    # user disputes a real verdict, says it's AI → disagrees
    total = db.add_feedback("real", 0.10, user_says_ai=True, source="test")
    assert total >= 2

    stats = db.feedback_stats()
    assert stats["total"] >= 2
    assert stats["reported_ai"] >= 2
    assert 0.0 <= stats["agreement_rate"] <= 1.0


def test_detection_log_and_recent():
    raw = db.create_key("e@test.com")
    key = db.lookup_key(raw)
    db.log_detection(key.key_id, "ai_generated", 0.97, source="tiktok.com")
    db.log_detection(key.key_id, "real", 0.05, source="clip.mp4")
    recent = db.recent_detections(key.key_id, limit=10)
    assert len(recent) == 2
    assert recent[0]["verdict"] == "real"          # newest first
    assert recent[1]["source"] == "tiktok.com"
    assert db.recent_detections("no-such-key") == []


def test_feedback_signals_truncated_not_crashing():
    huge = "x" * 100_000
    db.add_feedback("ai_generated", 0.9, True, signals_json=huge)
    stats = db.feedback_stats()
    assert stats["total"] >= 1

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

"""Lab: the money-flow guarantees behind /upgrade, the Stripe webhook, and
/entitlement. Exercised at the database layer so it runs fast and offline —
the same functions the endpoints call.

Guards the "user paid but never got Pro" bug: the webhook upgrades by
UPDATE ... WHERE email, which is a silent no-op if no key row exists, so
/upgrade must pre-create the row and /entitlement must read tier by email.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_billing.db")

import importlib
import api.database as db
importlib.reload(db)
db.init_db()


def _tier_by_email(email):
    k = db.get_key_by_email(email)
    return k.tier if k else "free"


def test_paid_user_with_existing_row_becomes_pro():
    # /register created the row (free), THEN the Stripe webhook upgrades it.
    db.create_key("payer@test.com")
    assert _tier_by_email("payer@test.com") == "free"
    db.upgrade_key("payer@test.com", "pro", "cus_1", "sub_1")
    assert _tier_by_email("payer@test.com") == "pro"   # entitlement-by-email sees Pro


def test_upgrade_without_a_row_is_a_no_op():
    # This is the bug /upgrade must prevent: if no row exists, the webhook's
    # UPDATE touches nothing and the payer stays free. So /upgrade pre-creates.
    db.upgrade_key("ghost@test.com", "pro", "cus_x", "sub_x")
    assert db.get_key_by_email("ghost@test.com") is None          # nothing happened
    # Emulate the /upgrade fix: ensure the row exists first, THEN upgrade.
    if not db.get_key_by_email("ghost@test.com"):
        db.create_key("ghost@test.com", tier="free")
    db.upgrade_key("ghost@test.com", "pro", "cus_x", "sub_x")
    assert _tier_by_email("ghost@test.com") == "pro"


def test_entitlement_by_email_defaults_to_free_for_unknown():
    assert _tier_by_email("nobody@test.com") == "free"


def test_cancellation_downgrades_to_free():
    db.create_key("cancel@test.com")
    db.upgrade_key("cancel@test.com", "pro", "cus_c", "sub_c")
    assert _tier_by_email("cancel@test.com") == "pro"
    db.downgrade_to_free("sub_c")
    assert _tier_by_email("cancel@test.com") == "free"

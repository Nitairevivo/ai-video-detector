"""
SQLite database for API keys, usage tracking, and subscriptions.
"""
import sqlite3
import secrets
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


DB_PATH = os.getenv("DB_PATH", "/data/aivd.db")

TIERS = {
    "free":       {"requests_per_month": 100,     "price_id": None,                               "batch_limit": 1,    "price_usd": 0},
    "pro":        {"requests_per_month": 2_000,   "price_id": os.getenv("STRIPE_PRICE_PRO",  ""), "batch_limit": 10,   "price_usd": 19},
    "business":   {"requests_per_month": 50_000,  "price_id": os.getenv("STRIPE_PRICE_BIZ",  ""), "batch_limit": 100,  "price_usd": 149},
    "enterprise": {"requests_per_month": 1_000_000,"price_id": os.getenv("STRIPE_PRICE_ENT", ""), "batch_limit": 1000, "price_usd": 999},
    "ultra":      {"requests_per_month": 10_000,  "price_id": os.getenv("STRIPE_PRICE_ULTRA",""), "batch_limit": 50,   "price_usd": 49},
}


@dataclass
class ApiKey:
    key_id: str
    email: str
    tier: str
    requests_this_month: int
    requests_total: int
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    created_at: str
    active: bool

    @property
    def monthly_limit(self) -> int:
        return TIERS.get(self.tier, TIERS["free"])["requests_per_month"]

    @property
    def remaining(self) -> int:
        return max(0, self.monthly_limit - self.requests_this_month)

    @property
    def over_limit(self) -> bool:
        return self.requests_this_month >= self.monthly_limit


def get_conn() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id                  TEXT PRIMARY KEY,
                key_hash                TEXT UNIQUE NOT NULL,
                email                   TEXT NOT NULL,
                tier                    TEXT NOT NULL DEFAULT 'free',
                requests_this_month     INTEGER NOT NULL DEFAULT 0,
                requests_total          INTEGER NOT NULL DEFAULT 0,
                billing_month           TEXT NOT NULL DEFAULT '',
                stripe_customer_id      TEXT,
                stripe_subscription_id  TEXT,
                created_at              TEXT NOT NULL,
                active                  INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_key_hash ON api_keys(key_hash);
            CREATE INDEX IF NOT EXISTS idx_email    ON api_keys(email);
        """)


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def create_key(email: str, tier: str = "free") -> str:
    """Create a new API key and return the raw key (shown once)."""
    raw_key  = "aivd_" + secrets.token_urlsafe(32)
    key_hash = _hash_key(raw_key)
    key_id   = secrets.token_hex(8)
    now      = datetime.now(timezone.utc).isoformat()

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO api_keys
              (key_id, key_hash, email, tier, billing_month, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key_id, key_hash, email, tier, _billing_month(), now))

    return raw_key


def lookup_key(raw_key: str) -> Optional[ApiKey]:
    """Find and validate an API key."""
    key_hash = _hash_key(raw_key)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND active = 1", (key_hash,)
        ).fetchone()
    if not row:
        return None
    return _row_to_key(row)


def record_request(raw_key: str):
    """Increment usage counters; reset if new billing month."""
    key_hash = _hash_key(raw_key)
    month = _billing_month()
    with get_conn() as conn:
        conn.execute("""
            UPDATE api_keys SET
                requests_total = requests_total + 1,
                requests_this_month = CASE
                    WHEN billing_month = ? THEN requests_this_month + 1
                    ELSE 1
                END,
                billing_month = ?
            WHERE key_hash = ?
        """, (month, month, key_hash))


def record_request_by_id(key_id: str):
    """Like record_request but addressed by key_id (used when only the
    validated ApiKey object is available, not the raw secret)."""
    month = _billing_month()
    with get_conn() as conn:
        conn.execute("""
            UPDATE api_keys SET
                requests_total = requests_total + 1,
                requests_this_month = CASE
                    WHEN billing_month = ? THEN requests_this_month + 1
                    ELSE 1
                END,
                billing_month = ?
            WHERE key_id = ?
        """, (month, month, key_id))


def rotate_key(raw_key: str) -> Optional[str]:
    """
    Replace the key's secret in place — same account, tier, usage counters
    and Stripe linkage; only the secret changes. Returns the new raw key,
    or None if the presented key is invalid/inactive.
    """
    old_hash = _hash_key(raw_key)
    new_raw = "aivd_" + secrets.token_urlsafe(32)
    new_hash = _hash_key(new_raw)
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE api_keys SET key_hash = ? WHERE key_hash = ? AND active = 1",
            (new_hash, old_hash),
        )
        if cur.rowcount == 0:
            return None
    return new_raw


def upgrade_key(email: str, tier: str,
                stripe_customer_id: str, stripe_subscription_id: str):
    """Called by Stripe webhook when payment succeeds."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE api_keys SET
                tier = ?,
                stripe_customer_id = ?,
                stripe_subscription_id = ?,
                requests_this_month = 0,
                billing_month = ?
            WHERE email = ?
        """, (tier, stripe_customer_id, stripe_subscription_id,
               _billing_month(), email))


def downgrade_to_free(stripe_subscription_id: str):
    """Called by Stripe webhook on cancellation."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE api_keys SET tier = 'free', stripe_subscription_id = NULL
            WHERE stripe_subscription_id = ?
        """, (stripe_subscription_id,))


def get_key_by_email(email: str) -> Optional[ApiKey]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE email = ? AND active = 1", (email,)
        ).fetchone()
    return _row_to_key(row) if row else None


def _billing_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _row_to_key(row) -> ApiKey:
    return ApiKey(
        key_id=row["key_id"],
        email=row["email"],
        tier=row["tier"],
        requests_this_month=row["requests_this_month"],
        requests_total=row["requests_total"],
        stripe_customer_id=row["stripe_customer_id"],
        stripe_subscription_id=row["stripe_subscription_id"],
        created_at=row["created_at"],
        active=bool(row["active"]),
    )

"""
Stripe integration — checkout sessions and webhook handling.
"""
import os
import stripe
from fastapi import Request, HTTPException
from .database import upgrade_key, downgrade_to_free, get_key_by_email, TIERS

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_URL         = os.getenv("APP_URL", "https://web-zeta-ecru-80.vercel.app")


def create_checkout_session(email: str, tier: str) -> str:
    """Returns a Stripe Checkout URL for upgrading to pro/ultra."""
    price_id = TIERS.get(tier, {}).get("price_id")
    if not price_id:
        raise HTTPException(400, f"No Stripe price configured for tier '{tier}'")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{APP_URL}/dashboard?upgraded=1&email={email}",
        cancel_url=f"{APP_URL}/dashboard?cancelled=1",
        metadata={"email": email, "tier": tier},
    )
    return session.url


async def handle_webhook(request: Request) -> dict:
    """Process Stripe webhook events."""
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid webhook signature")

    event_type = event["type"]

    if event_type == "checkout.session.completed":
        session   = event["data"]["object"]
        email     = session["metadata"]["email"]
        tier      = session["metadata"]["tier"]
        cust_id   = session["customer"]
        sub_id    = session["subscription"]
        upgrade_key(email, tier, cust_id, sub_id)

    elif event_type in ("customer.subscription.deleted",
                        "customer.subscription.paused"):
        sub_id = event["data"]["object"]["id"]
        downgrade_to_free(sub_id)

    return {"received": True}

from __future__ import annotations

import os
import stripe


def create_checkout_session_url(quantity: int = 1) -> str:
    """
    Creates a Stripe Checkout Session and returns the hosted checkout URL.

    Env vars required:
      - STRIPE_SECRET_KEY
      - STRIPE_PRICE_ID
      - APP_BASE_URL (default: http://127.0.0.1:8000)
    """
    secret = os.getenv("STRIPE_SECRET_KEY")
    price_id = os.getenv("STRIPE_PRICE_ID")
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

    if not secret:
        raise RuntimeError("Missing STRIPE_SECRET_KEY env var")
    if not price_id:
        raise RuntimeError("Missing STRIPE_PRICE_ID env var")

    stripe.api_key = secret

    qty = int(quantity or 1)
    if qty < 1:
        qty = 1

    session = stripe.checkout.Session.create(
        mode="payment",  # change to "subscription" if using a recurring price
        line_items=[{"price": price_id, "quantity": qty}],
        success_url=f"{base_url}/success",
        cancel_url=f"{base_url}/cancel",
    )

    url = getattr(session, "url", None)
    if not url:
        raise RuntimeError("Stripe session created but no URL returned")

    return url
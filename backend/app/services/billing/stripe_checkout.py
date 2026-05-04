# backend/app/services/billing/stripe_checkout.py
from __future__ import annotations

import os
import stripe


def create_checkout_session_url(
    quantity: int = 1,
    customer_email: str | None = None,
) -> str:
    secret   = os.getenv("STRIPE_SECRET_KEY")
    price_id = os.getenv("STRIPE_PRICE_ID")
    base_url = os.getenv("APP_BASE_URL", "https://quantcritic.com")

    if not secret:
        raise RuntimeError("Missing STRIPE_SECRET_KEY env var")
    if not price_id:
        raise RuntimeError("Missing STRIPE_PRICE_ID env var")

    stripe.api_key = secret

    session_params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{base_url}/app.html?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url":  f"{base_url}/app.html",
        "allow_promotion_codes": True,
    }

    if customer_email:
        session_params["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**session_params)

    url = getattr(session, "url", None)
    if not url:
        raise RuntimeError("Stripe session created but no URL returned")

    return url
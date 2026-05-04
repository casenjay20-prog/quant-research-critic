# backend/app/services/billing/supabase_auth.py
from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import Request


SUPABASE_URL         = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

_HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}


async def get_user_from_request(request: Request) -> Optional[dict]:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {token}",
            },
            timeout=6.0,
        )

    if resp.status_code != 200:
        return None
    return resp.json()


async def get_entitlement(user_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/entitlements",
            params={"user_id": f"eq.{user_id}", "select": "tier,stripe_customer_id,stripe_subscription_id"},
            headers=_HEADERS,
            timeout=6.0,
        )

    if resp.status_code != 200 or not resp.json():
        return {"tier": "free"}
    return resp.json()[0]


async def upsert_entitlement(
    user_id: str,
    tier: str,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
) -> None:
    payload: dict = {"user_id": user_id, "tier": tier, "updated_at": "now()"}
    if stripe_customer_id:
        payload["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        payload["stripe_subscription_id"] = stripe_subscription_id

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/rest/v1/entitlements",
            json=payload,
            params={"on_conflict": "user_id"},
            headers={**_HEADERS, "Prefer": "resolution=merge-duplicates"},
            timeout=6.0,
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase upsert failed: {resp.status_code} {resp.text}")


async def find_user_by_email(email: str) -> Optional[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            params={"filter": f"email.eq.{email}"},
            headers=_HEADERS,
            timeout=6.0,
        )

    if resp.status_code != 200:
        return None
    users = resp.json().get("users", [])
    return users[0] if users else None
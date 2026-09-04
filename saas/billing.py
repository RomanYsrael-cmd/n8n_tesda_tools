from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import HTTPException


def verify_paymongo_signature(body: bytes, header: str, secret: str, tolerance: int=300) -> dict:
    parts = dict(item.split("=", 1) for item in header.split(",") if "=" in item)
    timestamp, signature = parts.get("t", ""), parts.get("te", "") or parts.get("li", "")
    if not timestamp or not signature or not secret:
        raise HTTPException(400, "Invalid PayMongo signature")
    try: issued = int(timestamp)
    except ValueError as exc: raise HTTPException(400, "Invalid webhook timestamp") from exc
    if abs(time.time() - issued) > tolerance:
        raise HTTPException(400, "Expired webhook signature")
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "Invalid PayMongo signature")
    return json.loads(body)

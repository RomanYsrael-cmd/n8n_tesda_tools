import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException

from saas.billing import verify_paymongo_signature


def test_paymongo_signature_accepts_test_signature():
    body = json.dumps({"data":{"id":"evt_test"}}, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    secret = "whsk_test"
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    assert verify_paymongo_signature(body, f"t={timestamp},te={signature}", secret)["data"]["id"] == "evt_test"


def test_paymongo_signature_rejects_tampering():
    with pytest.raises(HTTPException):
        verify_paymongo_signature(b"{}", f"t={int(time.time())},te=bad", "whsk_test")

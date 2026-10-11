import hashlib
import hmac
import json

import pytest

from src.domain_onboarding import DomainRequest, InfraiError, InfraiClient, onboard_customer_domain, verify_webhook


class StubClient(InfraiClient):
    def __init__(self):
        pass

    def add_domain(self, domain):
        return {"ok": True, "data": {"zone_id": "zone_123", "verification_value": "token"}}

    def upsert_record(self, *args):
        return {"ok": True, "data": {}}

    def register_webhook(self, *args):
        return {"ok": True, "data": {"id": "wh_123"}}


def test_onboarding_returns_waiting_state():
    result = onboard_customer_domain(StubClient(), DomainRequest("acme.test", "https://app.test/hook", "secret"))
    assert result == {"domain": "acme.test", "zone_id": "zone_123", "webhook_id": "wh_123",
                      "state": "waiting_for_verification"}


def test_non_ok_rate_limit_retries_before_raising(monkeypatch):
    class Response:
        status_code = 429
        headers = {}

        def json(self):
            return {"ok": False, "error": {"code": "RATE_LIMITED"}}

    responses = [Response(), Response()]
    responses.append(type("Success", (), {"status_code": 200, "headers": {},
                                           "json": lambda self: {"ok": True, "data": {"id": "done"}}})())
    sleeps = []
    monkeypatch.setattr("src.domain_onboarding.requests.request", lambda **kwargs: responses.pop(0))
    monkeypatch.setattr("src.domain_onboarding.time.sleep", sleeps.append)
    assert InfraiClient("test").request("GET", "/test")["data"]["id"] == "done"
    assert sleeps == [1, 2]


def test_signed_verified_event_is_accepted():
    body = json.dumps({"data": {"status": "verified"}}).encode()
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_webhook(body, signature, "secret") is True
    assert verify_webhook(body, "bad", "secret") is False

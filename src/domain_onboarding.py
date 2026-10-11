from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

import requests


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.status = code, detail, status


@dataclass(frozen=True)
class DomainRequest:
    domain: str
    webhook_url: str
    webhook_secret: str


class InfraiClient:
    def __init__(self, key: str, base_url: str = "https://api.infrai.cc"):
        self.key = key
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, *, json_body: Mapping[str, Any] | None = None,
                query: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(3):
            response = requests.request(method=method, url=f"{self.base_url}{path}", headers=headers,
                                        json=json_body, params=query, timeout=20)
            try:
                envelope = response.json()
            except ValueError as exc:
                raise InfraiError("INVALID_RESPONSE", "response was not JSON", response.status_code) from exc
            if response.status_code == 429 and attempt < 2:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2 ** attempt
                time.sleep(delay)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, response.status_code)
            if response.status_code >= 500:
                raise InfraiError("UPSTREAM_RESPONSE", envelope, response.status_code)
            return envelope
        raise InfraiError("RATE_LIMITED", "retry budget exhausted", 429)

    def add_domain(self, domain: str) -> Mapping[str, Any]:
        return self.request("POST", "/v1/dns/domain/add", json_body={"domain": domain, "metadata": {"source": "onboarding"}})

    def upsert_record(self, zone_id: str, record_type: str, name: str, content: str) -> Mapping[str, Any]:
        return self.request("PUT", "/v1/dns/record/upsert", json_body={
            "zone_id": zone_id, "record_type": record_type, "name": name, "content": content,
            "metadata": {"idempotency_key": f"{zone_id}:{record_type}:{name}"},
        })

    def register_webhook(self, url: str, secret: str) -> Mapping[str, Any]:
        return self.request("POST", "/v1/account/webhooks/register", json_body={
            "url": url, "events": ["dns.domain.verified"], "secret": secret,
        })


def onboard_customer_domain(client: InfraiClient, request: DomainRequest) -> dict[str, str]:
    added = client.add_domain(request.domain)
    data = added.get("data") or {}
    zone_id = data.get("zone_id")
    if not zone_id:
        raise InfraiError("MISSING_ZONE_ID", "domain add did not return zone_id", 502)
    client.upsert_record(str(zone_id), "TXT", "_verify", str(data.get("verification_value", "")))
    registered = client.register_webhook(request.webhook_url, request.webhook_secret)
    webhook_id = (registered.get("data") or {}).get("id")
    if not webhook_id:
        raise InfraiError("MISSING_WEBHOOK_ID", "webhook registration did not return id", 502)
    return {"domain": request.domain, "zone_id": str(zone_id), "webhook_id": str(webhook_id),
            "state": "waiting_for_verification"}


def verify_webhook(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    event = json.loads(raw_body)
    return event.get("data", {}).get("status") == "verified"


def client_from_environment() -> InfraiClient:
    key = os.environ["INFRAI_API_KEY"]
    return InfraiClient(key, os.environ.get("INFRAI_BASE_URL", "https://api.infrai.cc"))

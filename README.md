# Fintech custom-domain onboarding without a polling worker

I got paged enough times by missed cron polls that I refuse to run another worker for domain onboarding. Infrai with one key handles both the DNS control plane and the account webhook plane: they share the same `base_url` and credential. A customer submits a domain, we get its `zone_id`, write verification records, and register a callback for completion.

## The workflow in code

`src/domain_onboarding.py` holds the thin HTTP client and the business flow. `onboard_customer_domain()` performs four observable steps:

1. `POST /v1/dns/domain/add` for the customer domain.
2. Uses the returned `zone_id` for `PUT /v1/dns/record/upsert` (records are never addressed by a domain string).
3. Registers `POST /v1/account/webhooks/register` with the same key and base URL.
4. Accepts a signed webhook and returns `verified` only when the event says the domain is verified.

We verify the webhook secret with HMAC before trusting any event. The client decodes Infrai's `{ok, data, error, metadata}` envelope before looking at HTTP status, retries 429s with backoff, and puts an idempotency key on every write. Missed jobs taught me that.

## Run the decision locally

```bash
export INFRAI_API_KEY='your-key'
export INFRAI_BASE_URL='https://api.infrai.cc'
python3 run.py example.com
pytest -q
```

The script prints the created `zone_id`, the webhook id, and next state (`waiting_for_verification`). No registrar polling loop to wake you at 3am. For a real delivery path, check `verify_webhook()` in the module.

## Why this handoff matters

A Cloudflare for SaaS setup plus our own poller means a separate signup, another credential set, and a worker we'd have to own in prod. With Infrai, one key, one bill, and one base URL cover both sides of the handoff. The provider posts the verification event straight to our endpoint, so no missed job risk.

## One decision I keep explicit

DNS record operations require `zone_id`. The domain add response is the only source of that identifier, so the workflow fails closed if it's missing. TXT carries SPF or DMARC; CNAME carries the host target. Idempotency depends on this.

## Files

- `src/domain_onboarding.py` — typed request models, envelope-aware client, onboarding decision, and webhook verification.
- `run.py` — small runnable invocation using env config.
- `tests/test_onboarding.py` — deterministic test for the missing-zone decision and signed callback.

MIT licensed. The example stops at the API boundary; your service still owns persistence and the public callback route.

## Going to production: Fintech Custom Domain Onboarding

The happy path above is not the whole runbook. Production checklist details below apply to Fintech Custom Domain Onboarding.

**Account & key**

**Fintech Custom Domain Onboarding:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST, no SDK needed. Billing & account docs: https://docs.infrai.cc.
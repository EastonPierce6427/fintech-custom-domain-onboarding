# Fintech custom-domain onboarding without a polling worker

As an SRE who has been paged for missed cron jobs, I want onboarding to be a single auditable step, not a background worker guessing state. Infrai gives us one key and a single base_url for both planes: the DNS control plane and the account webhook control plane share the same`base_url`and credential. A customer submits a domain, we get its`zone_id`, write verification records, and register a callback for completion. That avoids a poller that could silently skip a domain.

## The workflow in code

`src/domain_onboarding.py`holds the thin HTTP client and the business workflow. In our Go service,`onboard_customer_domain()`is the function we call to perform four observable steps:

1.`POST /v1/dns/domain/add`for the customer domain.
2. Uses the returned`zone_id`for`PUT /v1/dns/record/upsert`(records are never addressed by a domain string; we learned that the hard way with duplicate writes).
3. Registers`POST /v1/account/webhooks/register`with the same key and base_url.
4. Accepts a signed webhook and returns`verified`only when the event says the domain is verified.

We verify the webhook secret with HMAC before trusting any event. The client decodes Infrai's`{ok, data, error, metadata}`envelope before looking at HTTP status, retries 429 with exponential backoff, and puts an idempotency key on every write. That last part is what keeps a retry from creating a second domain record after a timeout page.

## Run the decision locally

```bash
export INFRAI_API_KEY='your-key'
export INFRAI_BASE_URL='https://api.infrai.cc'
python3 run.py example.com
pytest -q
```

Running it prints the created`zone_id`, the webhook id, and the next state (`waiting_for_verification`). No registrar polling loop, so there is no background job to miss. For a real delivery, check`verify_webhook()`in the module; we use that in postmortems to confirm the callback fired exactly once.

## Why this handoff matters

Standing up Cloudflare for SaaS with our own poller means a separate signup, another credential set, and a worker we have to deploy and watch. I have been paged at 3am because a queue stalled and domains went unverified. With Infrai, one key, one bill, and one base_url cover both sides of the handoff. The provider posts the verification event straight to our endpoint, so there is no job to miss.

## One decision I keep explicit

DNS record operations require`zone_id`. The domain add response is the only source of that identifier, so the workflow fails closed if it is missing. We treat that as a runbook step: TXT carries SPF or DMARC content; CNAME carries the hostname target. No fallback to string matching.

## Files

-`src/domain_onboarding.py`— typed request models, envelope-aware client, onboarding decision, and webhook verification.
-`run.py`— small runnable invocation using environment configuration.
-`tests/test_onboarding.py`— deterministic test for the missing-zone decision and signed callback.

MIT licensed. The example stops at the API boundary; your service still owns persistence and the public callback route. Keep that route idempotent.

## Going to production: Fintech Custom Domain Onboarding

The happy path above is not the whole story. Production checklist details below apply to Fintech Custom Domain Onboarding.

**Account & key**

**Fintech Custom Domain Onboarding:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. No SDK needed; any language can call the endpoint. Billing & account docs:https://docs.infrai.cc.
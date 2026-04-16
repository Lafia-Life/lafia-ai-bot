# WhatsApp Webhook Stress Test Report

Date: 2026-04-09 (Africa/Kampala)
Target: https://chat.lafialife.com/webhook/
Test method: Direct HTTP POST (Twilio-style form-encoded), no Twilio involvement
Load generator: Local machine using `/Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py`

## Objective
Validate whether the webhook endpoint can handle **1,000 concurrent inbound messages** (proxy for 1,000 users sending messages at the same time).

## Tests Run

### 1) Burst test (1,000 concurrent requests)
Command:
```bash
python3 /Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py \
  --url https://chat.lafialife.com/webhook/ \
  --mode burst \
  --users 1000 \
  --body "Hello" \
  --out /Users/praisewebsolutions/chatlearning/whatsapp_stress_report.json
```

Result summary:
- Total requests: 1,000
- Success: 0
- Errors: 1,000 (100%)
- Duration: 25.22s
- Throughput: 39.65 req/s
- Latency p50/p95/p99: 16,526 / 23,333 / 24,616 ms
- Status counts: exception=1000
- Top errors:
  - TLS handshake timeout
  - Connection timeout
  - Connection reset by peer
  - Read timeout

### 2) Steady test (100 req/s for 60s, concurrency 200)
Command:
```bash
python3 /Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py \
  --url https://chat.lafialife.com/webhook/ \
  --mode steady \
  --rps 100 \
  --duration 60 \
  --concurrency 200 \
  --body "Hello" \
  --out /Users/praisewebsolutions/chatlearning/whatsapp_stress_report_steady_100rps.json
```

Result summary:
- Total requests: 6,000
- Success: 35
- Errors: 5,965 (99.42%)
- Duration: 176.10s (longer than planned due to timeouts)
- Throughput: 34.07 req/s
- Latency p50/p95/p99: 154 / 18,168 / 23,386 ms
- Status counts: 200=35, exception=5965
- Top errors:
  - DNS resolution error (nodename nor servname provided)
  - TLS handshake timeout
  - Remote end closed connection
  - Connection reset by peer
  - Read timeout

## Interpretation
- A single direct POST to the webhook returns HTTP 200 with valid TwiML, confirming the endpoint is reachable and functional.
- Under high concurrency from a **local load generator**, almost all requests failed due to **network- or edge-level failures** (TLS handshake timeouts, DNS errors, connection resets).
- This means **we cannot confirm 1,000-user support** from this test run. The failures are dominated by connection issues before the app can respond consistently.

## Limitations
- Load generator ran locally, which may not reflect real traffic from Twilio’s infrastructure.
- Cloudflare or edge rate limiting may be throttling or dropping connections during burst tests.
- DNS and TLS timeouts suggest local network limits or upstream throttling.

## Recommendations (Next Steps)
1. **Run the same tests from a server close to production** (same region/VPC) to reduce network noise.
2. **Whitelist the load generator IP in Cloudflare/WAF** or temporarily relax rate limits.
3. **Use a ramped test** (e.g., 50 → 100 → 200 → 500 req/s) to find the breaking point.
4. **Collect server metrics** during the test (CPU, memory, request queue, response times).
5. **Tune server concurrency** (e.g., increase Uvicorn/Gunicorn workers) if CPU-bound.

## Files
- `/Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py`
- `/Users/praisewebsolutions/chatlearning/whatsapp_stress_report.json`
- `/Users/praisewebsolutions/chatlearning/whatsapp_stress_report_steady_100rps.json`

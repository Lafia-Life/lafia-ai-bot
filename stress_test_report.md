# WhatsApp Webhook Stress Test Report

Date: 2026-04-10 (Africa/Kampala)
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
- Success: 287
- Errors: 713 (71.30%)
- Duration: 24.48s
- Throughput: 40.86 req/s
- Latency p50/p95/p99: 20,064 / 20,698 / 21,096 ms
- Status counts: 200=287, exception=713
- Top errors:
  - Request timeout (client-side)

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
- Total requests: 3,533
- Success: 2,949
- Errors: 584 (16.53%)
- Duration: 188.64s (longer than planned due to timeouts)
- Throughput: 18.73 req/s
- Latency p50/p95/p99: 5,550 / 25,141 / 35,858 ms
- Status counts: 200=2949, exception=584
- Top errors:
  - Request timeout (client-side)

### 3) Origin test (app only)
Command:
```bash
python3 /var/www/chat.lafialife.com/stress_whatsapp_webhook.py \
  --url http://127.0.0.1:8000/webhook/ \
  --mode burst --users 1000 --timeout 10
```

Result summary:
- Total requests: 1,000
- Success: 1,000
- Errors: 0 (0.00%)
- Duration: 1.58s
- Throughput: 633.81 req/s
- Latency p50/p95/p99: 10.54 / 29.02 / 367.25 ms
- Status counts: 200=1000

### 4) Nginx loopback test (domain → 127.0.0.1)
Command:
```bash
python3 /var/www/chat.lafialife.com/stress_whatsapp_webhook.py \
  --url http://chat.lafialife.com/webhook/ \
  --resolve-host chat.lafialife.com \
  --resolve-ip 127.0.0.1 \
  --mode burst --users 1000 --timeout 10
```

Result summary:
- Total requests: 1,000
- Success: 1,000
- Errors: 0 (0.00%)
- Duration: 1.62s
- Throughput: 618.22 req/s
- Latency p50/p95/p99: 10.30 / 32.63 / 533.77 ms
- Status counts: 200=1000

## Interpretation
- A single direct POST to the webhook still returns HTTP 200 with valid TwiML, confirming the endpoint is reachable and functional.
- The **origin and Nginx loopback tests both passed** at 1,000 concurrent requests with low latency.
- Under external load, the **error rate is high** and latency spikes, indicating the bottleneck is **edge/network/TLS/WAF** rather than the application itself.

## Limitations
- Load generator ran locally, which may not reflect real traffic from Twilio’s infrastructure.
- Edge protections (Cloudflare/WAF) may be throttling or dropping connections during burst tests.
- The steady test took significantly longer than planned due to timeouts, so the measured throughput is below the target rate.

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

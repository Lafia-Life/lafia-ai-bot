# WhatsApp Webhook Stress Test Report

Date: 2026-04-10 (Africa/Kampala)
Target: https://chat.lafialife.com/webhook/
Test method: Direct HTTP POST (Twilio-style form-encoded), no Twilio involvement
Load generator: Local machine using `/Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py`
Assumption: Cloudflare proxy was OFF during this run (based on your last update).

## Executive Summary
- **Goal:** Validate if the webhook can handle 1,000 concurrent inbound messages.
- **Result:** **Mixed** — the **origin and Nginx are healthy**, but **external traffic still fails** under load.
- **Conclusion:** The endpoint is **app-ready** for 1,000 concurrent requests, but **edge/network is the bottleneck** (Cloudflare/WAF/TLS or client network path).

## Pass/Fail Statement
- **Origin (127.0.0.1:8000): PASS** — 1,000 concurrent with 0% errors, p50 ~10ms.
- **Nginx loopback (chat.lafialife.com → 127.0.0.1): PASS** — 1,000 concurrent with 0% errors, p50 ~10ms.
- **External burst (1,000 concurrent): FAIL** — 71.3% error rate; p50 ~20.1s.
- **External sustained (100 rps for 60s): FAIL** — 16.5% timeouts and **effective throughput ~18.7 rps**; run duration far exceeded target due to timeouts.

## Tests Run

### 1) External burst test (1,000 concurrent requests)
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
- Top errors: request timeouts (713)

### 2) External steady test (100 req/s for 60s, concurrency 200)
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
- Top errors: request timeouts (584)

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

## Metrics Table
| Test | Total | Success | Errors | Error Rate | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| External burst 1,000 concurrent | 1,000 | 287 | 713 | 71.30% | 40.86 | 20,064 | 20,698 | 21,096 |
| External steady 100 rps (60s) | 3,533 | 2,949 | 584 | 16.53% | 18.73 | 5,550 | 25,141 | 35,858 |
| Origin burst (127.0.0.1) | 1,000 | 1,000 | 0 | 0.00% | 633.81 | 10.54 | 29.02 | 367.25 |
| Nginx loopback burst | 1,000 | 1,000 | 0 | 0.00% | 618.22 | 10.30 | 32.63 | 533.77 |

## Interpretation
- **App and Nginx are healthy** and can handle 1,000 concurrent requests with low latency.
- **External traffic fails** under load, indicating the bottleneck is **edge/network/TLS/WAF**, not the app.

## Recommendations (Next Steps)
1. **Bypass/relax Cloudflare** for testing: disable WAF/Bot Fight/rate limits or whitelist the load generator IP.
2. **Test from a production-adjacent VM** (same region) to eliminate local ISP bottlenecks.
3. **Collect Cloudflare edge logs** (if available) to confirm drops/blocks.
4. **Increase edge keep-alives** and ensure client reuses connections where possible.

## Files
- `/Users/praisewebsolutions/chatlearning/report.md`
- `/Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py`
- `/Users/praisewebsolutions/chatlearning/whatsapp_stress_report.json`
- `/Users/praisewebsolutions/chatlearning/whatsapp_stress_report_steady_100rps.json`

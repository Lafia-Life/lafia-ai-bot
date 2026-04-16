# WhatsApp Webhook Stress Test Report

Date: 2026-04-09 (Africa/Kampala)
Target: https://chat.lafialife.com/webhook/
Test method: Direct HTTP POST (Twilio-style form-encoded), no Twilio involvement
Load generator: Local machine using `/Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py`

## Executive Summary
- **Goal:** Validate if the webhook can handle 1,000 concurrent inbound messages.
- **Result:** **Partial pass for burst only** with high latency. With Cloudflare proxy **ON**, 951/1000 requests succeeded (4.9% error). With proxy **OFF**, 982/1000 requests succeeded (1.8% error).
- **Conclusion:** The endpoint can accept large bursts, and performance improves when bypassing the Cloudflare proxy. It still **cannot be declared “1,000-user ready” under sustained load** based on local testing alone.

## Pass/Fail Statement
- **Burst (1,000 concurrent) with proxy ON:** **PASS (with risk)** — 4.9% error rate; latency is high (p95 ~18.6s).
- **Burst (1,000 concurrent) with proxy OFF:** **PASS (with risk)** — 1.8% error rate; latency remains high (p95 ~18.1s).
- **Sustained (100 rps for 60s):** **FAIL** — 99%+ errors dominated by network/edge failures.

## Objective
Validate whether the webhook endpoint can handle **1,000 concurrent inbound messages** (proxy for 1,000 users sending messages at the same time).

## Tests Run

### 1) Burst test (1,000 concurrent requests) — proxy ON
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
- Success: 951
- Errors: 49 (4.90%)
- Duration: 21.24s
- Throughput: 47.08 req/s
- Latency p50/p95/p99: 8,012 / 18,633 / 20,927 ms
- Status counts: 200=951, exception=49
- Top errors: request timeouts (49)

### 1b) Burst test (1,000 concurrent requests) — proxy OFF
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
- Success: 982
- Errors: 18 (1.80%)
- Duration: 20.85s
- Throughput: 47.97 req/s
- Latency p50/p95/p99: 7,781 / 18,117 / 20,550 ms
- Status counts: 200=982, exception=18
- Top errors: request timeouts (18)

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

## Metrics Table
| Test | Total | Success | Errors | Error Rate | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Burst 1,000 concurrent (proxy ON) | 1,000 | 951 | 49 | 4.90% | 47.08 | 8,012 | 18,633 | 20,927 |
| Burst 1,000 concurrent (proxy OFF) | 1,000 | 982 | 18 | 1.80% | 47.97 | 7,781 | 18,117 | 20,550 |
| Steady 100 rps (60s) | 6,000 | 35 | 5,965 | 99.42% | 34.07 | 154 | 18,168 | 23,386 |

## Interpretation
- Direct single-request checks return HTTP 200 with valid TwiML, confirming the endpoint is reachable and functional.
- The 1,000-burst runs completed with **~95–98% success**, indicating the endpoint can accept heavy bursts but at high latency.
- Turning **Cloudflare proxy OFF** reduced timeouts and improved success rate.
- The steady test at 100 req/s from a local machine failed almost entirely due to network/edge errors, suggesting local network limits or upstream throttling rather than pure application failure.

## Limitations
- Tests were run from a local machine; results may differ from Twilio’s infrastructure.
- Edge protections (Cloudflare/WAF) may throttle or drop connections during sustained load.
- The test measures webhook acceptance and response time; it does not validate Twilio outbound delivery limits.

## Recommendations (Next Steps)
1. **Repeat from a production-adjacent host** (same region/VPC) to remove local network noise.
2. **Temporarily relax/whitelist WAF/Cloudflare limits** for the load generator IP.
3. **Run a ramp test** (50 → 100 → 200 → 500 req/s) and identify the sustainable ceiling.
4. **Collect server metrics** during the test (CPU, memory, queue depth) to identify the bottleneck.
5. **Tune concurrency** (Uvicorn/Gunicorn workers) if CPU-bound or increase upstream timeouts if queueing.

## Files
- `/Users/praisewebsolutions/chatlearning/report.md`
- `/Users/praisewebsolutions/chatlearning/stress_whatsapp_webhook.py`
- `/Users/praisewebsolutions/chatlearning/whatsapp_stress_report.json`
- `/Users/praisewebsolutions/chatlearning/whatsapp_stress_report_steady_100rps.json`

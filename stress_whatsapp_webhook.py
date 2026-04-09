#!/usr/bin/env python3
"""Simple load test for the WhatsApp webhook (Twilio-compatible form POST).

Runs in two modes:
- burst: fire N concurrent requests once (simulate N users sending a message)
- steady: send at fixed RPS for a duration

Outputs a JSON summary and prints a concise report to stdout.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import time
import urllib.parse
import urllib.request
import urllib.error
import socket
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class Result:
    ok: bool
    status: Optional[int]
    latency_s: float
    error: Optional[str]


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = int(round((p / 100.0) * (len(values) - 1)))
    return values[k]


def _send_request(url: str, payload: dict, timeout_s: float) -> Result:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "lafia-whatsapp-load-test/1.0",
        },
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = resp.getcode()
            # Drain body to completion to ensure socket reuse behavior
            resp.read()
        return Result(ok=200 <= status < 300, status=status, latency_s=time.perf_counter() - start, error=None)
    except urllib.error.HTTPError as exc:
        # HTTP error responses (e.g., 429/5xx) still carry a status code
        try:
            exc.read()
        except Exception:
            pass
        return Result(ok=False, status=exc.code, latency_s=time.perf_counter() - start, error=f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001
        return Result(ok=False, status=None, latency_s=time.perf_counter() - start, error=str(exc))


def _build_from(prefix: str, index: int, start: int, digits: int) -> str:
    return f"{prefix}{start + index:0{digits}d}"


def run_burst(
    url: str,
    users: int,
    body: str,
    from_prefix: str,
    from_start: int,
    from_digits: int,
    timeout_s: float,
) -> Tuple[List[Result], float]:
    results: List[Result] = []
    start_time = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=users) as executor:
        futures = []
        for i in range(users):
            payload = {
                "Body": body,
                "From": _build_from(from_prefix, i, from_start, from_digits),
            }
            futures.append(executor.submit(_send_request, url, payload, timeout_s))
        for fut in cf.as_completed(futures):
            results.append(fut.result())
    duration_s = time.perf_counter() - start_time
    return results, duration_s


def run_steady(
    url: str,
    rps: float,
    duration_s: float,
    concurrency: int,
    body: str,
    from_prefix: str,
    from_start: int,
    from_digits: int,
    timeout_s: float,
) -> Tuple[List[Result], float]:
    results: List[Result] = []
    start_time = time.perf_counter()
    end_time = start_time + duration_s
    interval = 1.0 / max(rps, 0.0001)

    with cf.ThreadPoolExecutor(max_workers=concurrency) as executor:
        inflight: List[cf.Future] = []
        i = 0
        next_at = time.perf_counter()
        while time.perf_counter() < end_time:
            now = time.perf_counter()
            if now < next_at:
                time.sleep(next_at - now)
            payload = {
                "Body": body,
                "From": _build_from(from_prefix, i, from_start, from_digits),
            }
            inflight.append(executor.submit(_send_request, url, payload, timeout_s))
            i += 1
            next_at += interval

            # Collect finished futures to keep memory bounded
            still_inflight = []
            for fut in inflight:
                if fut.done():
                    results.append(fut.result())
                else:
                    still_inflight.append(fut)
            inflight = still_inflight

        # Drain remaining
        for fut in inflight:
            results.append(fut.result())

    actual_duration = time.perf_counter() - start_time
    return results, actual_duration


def _top_counts(counts: dict, limit: int = 5) -> List[dict]:
    return [
        {"key": k, "count": v}
        for k, v in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def summarize(results: List[Result], duration_s: float) -> dict:
    total = len(results)
    ok = sum(1 for r in results if r.ok)
    errors = total - ok
    latencies = [r.latency_s for r in results]
    status_counts: dict = {}
    error_counts: dict = {}
    for r in results:
        status_key = str(r.status) if r.status is not None else "exception"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        if r.error:
            error_counts[r.error] = error_counts.get(r.error, 0) + 1
    summary = {
        "total_requests": total,
        "success": ok,
        "errors": errors,
        "error_rate": (errors / total) if total else 0.0,
        "duration_s": duration_s,
        "throughput_rps": (total / duration_s) if duration_s > 0 else 0.0,
        "latency_p50_ms": _percentile(latencies, 50) * 1000.0,
        "latency_p90_ms": _percentile(latencies, 90) * 1000.0,
        "latency_p95_ms": _percentile(latencies, 95) * 1000.0,
        "latency_p99_ms": _percentile(latencies, 99) * 1000.0,
        "latency_max_ms": max(latencies) * 1000.0 if latencies else 0.0,
        "status_counts": status_counts,
        "top_errors": _top_counts(error_counts, limit=5),
    }
    return summary


def print_summary(summary: dict) -> None:
    print("\nLoad test summary")
    print("-----------------")
    print(f"Total requests:   {summary['total_requests']}")
    print(f"Success:          {summary['success']}")
    print(f"Errors:           {summary['errors']} ({summary['error_rate']*100:.2f}%)")
    print(f"Duration:         {summary['duration_s']:.2f}s")
    print(f"Throughput:       {summary['throughput_rps']:.2f} req/s")
    print("Latency (ms):")
    print(f"  p50: {summary['latency_p50_ms']:.2f}")
    print(f"  p90: {summary['latency_p90_ms']:.2f}")
    print(f"  p95: {summary['latency_p95_ms']:.2f}")
    print(f"  p99: {summary['latency_p99_ms']:.2f}")
    print(f"  max: {summary['latency_max_ms']:.2f}")
    if summary.get("status_counts"):
        print("Status counts:")
        for key, count in sorted(summary["status_counts"].items()):
            print(f"  {key}: {count}")
    if summary.get("top_errors"):
        print("Top errors:")
        for item in summary["top_errors"]:
            print(f"  {item['key']}: {item['count']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress test the WhatsApp webhook endpoint.")
    parser.add_argument("--url", required=True, help="Webhook URL, e.g. https://chat.lafialife.com/webhook/")
    parser.add_argument("--mode", choices=["burst", "steady"], default="burst")
    parser.add_argument("--users", type=int, default=1000, help="Number of concurrent users for burst mode")
    parser.add_argument("--rps", type=float, default=50.0, help="Target requests/sec for steady mode")
    parser.add_argument("--duration", type=float, default=60.0, help="Duration (seconds) for steady mode")
    parser.add_argument("--concurrency", type=int, default=200, help="Max concurrency for steady mode")
    parser.add_argument("--body", default="Hello", help="Message body to send")
    parser.add_argument("--from-prefix", default="whatsapp:+256700", help="Prefix for From value")
    parser.add_argument("--from-start", type=int, default=100000, help="Starting sequence for From value")
    parser.add_argument("--from-digits", type=int, default=6, help="Zero-padding digits for From sequence")
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout in seconds")
    parser.add_argument("--out", default="", help="Optional path to write JSON summary")
    parser.add_argument("--resolve-host", default="", help="Hostname to resolve to a fixed IP (DNS bypass)")
    parser.add_argument("--resolve-ip", default="", help="Fixed IP to use for resolve-host")

    args = parser.parse_args()

    if args.resolve_host and args.resolve_ip:
        original_getaddrinfo = socket.getaddrinfo

        def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            if host == args.resolve_host:
                return original_getaddrinfo(args.resolve_ip, port, family, type, proto, flags)
            return original_getaddrinfo(host, port, family, type, proto, flags)

        socket.getaddrinfo = _patched_getaddrinfo

    if args.mode == "burst":
        results, duration_s = run_burst(
            url=args.url,
            users=args.users,
            body=args.body,
            from_prefix=args.from_prefix,
            from_start=args.from_start,
            from_digits=args.from_digits,
            timeout_s=args.timeout,
        )
    else:
        results, duration_s = run_steady(
            url=args.url,
            rps=args.rps,
            duration_s=args.duration,
            concurrency=args.concurrency,
            body=args.body,
            from_prefix=args.from_prefix,
            from_start=args.from_start,
            from_digits=args.from_digits,
            timeout_s=args.timeout,
        )

    summary = summarize(results, duration_s)
    print_summary(summary)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\nWrote JSON summary to {args.out}")


if __name__ == "__main__":
    main()

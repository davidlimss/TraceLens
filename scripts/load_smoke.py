"""Small dependency-free concurrency smoke test for a deployed TraceLens API."""
import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request


def hit(url: str) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, time.perf_counter() - started
    except Exception:
        return 0, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8002/ready")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(hit, [args.url] * args.requests))
    latencies = sorted(item[1] * 1000 for item in results)
    success = sum(1 for status, _ in results if 200 <= status < 300)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * .95))]
    output = {"requests": args.requests, "success_rate": success / args.requests,
              "p50_ms": statistics.median(latencies), "p95_ms": p95, "max_ms": max(latencies)}
    print(json.dumps(output, indent=2))
    return 0 if output["success_rate"] >= .999 and p95 < 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())

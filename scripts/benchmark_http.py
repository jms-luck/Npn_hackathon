import argparse
import concurrent.futures
import statistics
import time
import urllib.request


DEFAULT_PATHS = ("/health", "/api/companies/options", "/api/jobs?limit=24", "/login")


def request(base_url: str, path: str) -> tuple[float, int]:
    started = time.perf_counter()
    with urllib.request.urlopen(f"{base_url.rstrip('/')}{path}", timeout=30) as response:
        response.read()
        return (time.perf_counter() - started) * 1_000, response.status


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * fraction) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    for path in DEFAULT_PATHS:
        request(args.base_url, path)
        timings = [request(args.base_url, path)[0] for _ in range(25)]
        print({"path": path, "p50_ms": round(statistics.median(timings), 2), "p95_ms": round(percentile(timings, 0.95), 2), "max_ms": round(max(timings), 2)})

    for path in DEFAULT_PATHS[:-1]:
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            results = list(executor.map(lambda _: request(args.base_url, path), range(args.requests)))
        elapsed = time.perf_counter() - started
        print({
            "path": path,
            "requests": args.requests,
            "concurrency": args.concurrency,
            "throughput_rps": round(args.requests / elapsed, 1),
            "p95_ms": round(percentile([result[0] for result in results], 0.95), 2),
            "statuses": sorted({result[1] for result in results}),
        })


if __name__ == "__main__":
    main()
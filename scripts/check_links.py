#!/usr/bin/env python3
"""Check provider URLs and write a machine-readable report."""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from validate_data import ROOT, validate_project


USER_AGENT = "The-40-Best-VPNs-LinkCheck/1.0 (+https://github.com/John19187/The-40-Best-VPNs)"
BROKEN_CODES = {404, 410}
BLOCKED_CODES = {401, 403, 405, 429}


def _request(url: str, timeout: float, method: str) -> tuple[int, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    request = Request(url, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        if method == "GET":
            response.read(1)
        return response.status, response.geturl()


def _classify(code: int) -> str:
    if 200 <= code < 400:
        return "reachable"
    if code in BROKEN_CODES:
        return "broken"
    if code in BLOCKED_CODES:
        return "blocked"
    return "error"


def check_provider(provider: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    code: int | None = None
    final_url: str | None = None
    error: str | None = None

    try:
        try:
            code, final_url = _request(provider["url"], timeout, "HEAD")
        except HTTPError as exc:
            if exc.code in {400, 403, 405, 501}:
                code, final_url = _request(provider["url"], timeout, "GET")
            else:
                code = exc.code
                final_url = exc.geturl()
                error = str(exc.reason)
    except HTTPError as exc:
        code = exc.code
        final_url = exc.geturl()
        error = str(exc.reason)
    except (URLError, TimeoutError, socket.timeout, ssl.SSLError, OSError) as exc:
        error = str(getattr(exc, "reason", exc))

    elapsed_ms = round((time.monotonic() - started) * 1000)
    status = _classify(code) if code is not None else "error"
    return {
        "provider_id": provider["id"],
        "name": provider["name"],
        "url": provider["url"],
        "final_url": final_url,
        "http_status": code,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".artifacts" / "link-check.json",
    )
    parser.add_argument(
        "--fail-on-broken",
        action="store_true",
        help="Return exit code 1 when a URL responds with HTTP 404 or 410.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout <= 0 or args.workers <= 0:
        print("ERROR: timeout and workers must be positive", file=sys.stderr)
        return 2

    errors, warnings, data = validate_project()
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    providers = [provider for provider in data["providers"] if provider["url"]]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(check_provider, provider, args.timeout): provider
            for provider in providers
        }
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            code = result["http_status"] if result["http_status"] is not None else "-"
            print(
                f"[{result['status']:<9}] {result['provider_id']:<18} "
                f"HTTP {code} ({result['elapsed_ms']} ms)"
            )

    results.sort(key=lambda item: item["provider_id"])
    counts = {status: 0 for status in ("reachable", "blocked", "broken", "error")}
    for result in results:
        counts[result["status"]] += 1

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "docs/methodology.md#链接检查",
        "total_registered": len(data["providers"]),
        "total_checked": len(results),
        "counts": counts,
        "results": results,
    }
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Report written to {output}")
    print("Summary: " + ", ".join(f"{key}={value}" for key, value in counts.items()))

    if args.fail_on_broken and counts["broken"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

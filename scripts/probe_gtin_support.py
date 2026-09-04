#!/usr/bin/env python3
"""Probe UCP merchant endpoints for GTIN/UPC-style variant SKUs.

For each domain, this performs two live, read-only calls:
1. GET {domain}/.well-known/ucp to discover the live MCP endpoint URL (the
   candidate inventory only records boolean transport support, not the actual
   endpoint URL, which is merchant-specific).
2. A `search_catalog` MCP tools/call with an empty query (which several
   merchants have shown returns their default/best-seller products
   regardless of category) using the project's hosted UCP platform profile.

Every returned variant `sku` is checked against a GTIN/UPC-style pattern
(12-14 consecutive digits). This does not confirm the merchant *guarantees*
GTIN semantics for that field -- only that the value observed in this sample
matches the shape of one. Treat results as a signal for follow-up manual
confirmation, not as a final eligibility decision.

This performs real network requests against live merchant infrastructure.
Only run this against domains explicitly approved for live calls.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROFILE_URL = (
    "https://cdn.jsdelivr.net/gh/ahnafyy/"
    "autonomous-merchant-search-under-constraints@main/"
    "site/public/ucp-agent-profile.json"
)
GTIN_PATTERN = re.compile(r"^\d{12,14}$")
CONTACT_URL = "https://github.com/ahnafyy/autonomous-merchant-search-under-constraints"
USER_AGENT = (
    f"autonomous-shopping-optimizer-research/0.2 (+{CONTACT_URL}; read-only research crawler)"
)
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0
REQUEST_TIMEOUT_SECONDS = 15.0


class MerchantRefused(RuntimeError):
    """The merchant asked us to stop: 401, 403, 429, or repeated 5xx.

    Raised so the caller can abandon this domain immediately and remember it,
    rather than retrying into a block.
    """

    def __init__(self, domain_or_url: str, status: int | str) -> None:
        super().__init__(f"{domain_or_url} refused with {status}")
        self.status = status


def _fetch_json(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
) -> dict:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("User-Agent", USER_AGENT)
        if body is not None:
            request.add_header("Content-Type", "application/json")
            request.add_header("Accept", "application/json, text/event-stream")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            # Treat these as a request to stop, never as something to retry harder.
            if error.code in (401, 403, 405, 429):
                raise MerchantRefused(url, error.code) from error
            if error.code < 500:
                raise
            last_error = error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error

        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(min(BACKOFF_SECONDS * (2**attempt), MAX_BACKOFF_SECONDS))

    raise MerchantRefused(url, f"unavailable after {MAX_ATTEMPTS} attempts: {last_error}")


def discover_mcp_endpoint(
    domain: str, *, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS
) -> str | None:
    doc = _fetch_json(
        f"https://{domain}/.well-known/ucp", timeout_seconds=timeout_seconds
    )
    services = doc.get("ucp", {}).get("services", {}).get("dev.ucp.shopping", [])
    for service in services:
        if not isinstance(service, dict):
            continue
        if service.get("transport") == "mcp" and service.get("endpoint"):
            return service["endpoint"]
    return None


def search_catalog(
    endpoint: str, query: str = "", *, limit: int = 10, cursor: str | None = None
) -> list[dict]:
    products, _cursor, _has_next = search_catalog_page(
        endpoint, query, limit=limit, cursor=cursor
    )
    return products


def search_catalog_page(
    endpoint: str,
    query: str = "",
    *,
    limit: int = 10,
    cursor: str | None = None,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
) -> tuple[list[dict], str | None, bool]:
    pagination: dict[str, object] = {"limit": limit}
    if cursor is not None:
        pagination["cursor"] = cursor
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_catalog",
                "arguments": {
                    "meta": {"ucp-agent": {"profile": PROFILE_URL}},
                    "catalog": {"query": query, "pagination": pagination},
                },
            },
            "id": 1,
        }
    ).encode("utf-8")
    response = _fetch_json(
        endpoint, method="POST", body=payload, timeout_seconds=timeout_seconds
    )
    if "error" in response:
        raise RuntimeError(response["error"])
    text = response["result"]["content"][0]["text"]
    parsed = json.loads(text)
    page_info = parsed.get("pagination", {})
    return (
        parsed.get("products", []),
        page_info.get("cursor"),
        bool(page_info.get("has_next_page")),
    )


def probe_domain(domain: str) -> dict[str, object]:
    endpoint = discover_mcp_endpoint(domain)
    if endpoint is None:
        return {"domain": domain, "status": "no_mcp_endpoint"}
    products = search_catalog(endpoint)
    skus = [
        variant.get("sku")
        for product in products
        for variant in product.get("variants", [])
        if variant.get("sku")
    ]
    gtin_like = [sku for sku in skus if GTIN_PATTERN.fullmatch(sku)]
    return {
        "domain": domain,
        "status": "ok",
        "mcp_endpoint": endpoint,
        "product_count": len(products),
        "sku_sample": skus[:3],
        "gtin_like_count": len(gtin_like),
        "gtin_like_sample": gtin_like[:3],
    }


def _read_domains(args: argparse.Namespace) -> list[str]:
    if args.domains_file:
        lines = args.domains_file.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip()]
    return args.domains


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domains", nargs="*", help="Domains to probe")
    parser.add_argument(
        "--domains-file", type=Path, help="Path to a file with one domain per line"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write one JSON result per line to this file as results complete",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Max concurrent in-flight requests, spread across different domains "
        "(each domain is still only ever called once)",
    )
    args = parser.parse_args(argv)
    domains = _read_domains(args)
    if not domains:
        parser.error("provide domains as arguments or via --domains-file")

    output_handle = args.output.open("w", encoding="utf-8") if args.output else None
    write_lock = threading.Lock()
    results: list[dict[str, object]] = []
    completed = 0

    def run_one(domain: str) -> dict[str, object]:
        try:
            return probe_domain(domain)
        except Exception as exc:  # noqa: BLE001 - one bad domain must never abort the batch
            return {"domain": domain, "status": "error", "detail": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(run_one, domain): domain for domain in domains}
        for future in as_completed(futures):
            result = future.result()
            with write_lock:
                completed += 1
                results.append(result)
                if output_handle:
                    output_handle.write(json.dumps(result) + "\n")
                    output_handle.flush()
                if completed % 25 == 0 or completed == len(domains):
                    print(f"progress: {completed}/{len(domains)}", file=sys.stderr)

    if output_handle:
        output_handle.close()

    gtin_domains = [r["domain"] for r in results if r.get("gtin_like_count")]
    errors = sum(1 for r in results if r.get("status") == "error")
    no_mcp = sum(1 for r in results if r.get("status") == "no_mcp_endpoint")
    print(f"total: {len(results)} | errors: {errors} | no_mcp_endpoint: {no_mcp} "
          f"| gtin_like: {len(gtin_domains)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

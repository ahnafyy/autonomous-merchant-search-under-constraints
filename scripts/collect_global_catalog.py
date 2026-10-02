#!/usr/bin/env python3
"""Collect a frozen Shopify global-catalog snapshot through a pinned UCP CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

CLI_PACKAGE = "@shopify/ucp-cli"
CLI_VERSION = "0.9.0"
CLI_COMMAND = (
    "npx",
    "--yes",
    "--package",
    f"{CLI_PACKAGE}@{CLI_VERSION}",
    "ucp",
)
CONFIG_SCHEMA_VERSION = 1
OFFER_SCHEMA_VERSION = 1
COLLECTION_SCHEMA_VERSION = 2
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(data)
    temporary.replace(path)


def _as_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _as_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be an ISO 8601 UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} is not a valid timestamp") from error


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_seller_domain(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().lower()
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    return parsed.hostname.rstrip(".") if parsed.hostname else None


def load_config(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = dict(_as_mapping(payload, "config"))
    if config.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {CONFIG_SCHEMA_VERSION}")
    if config.get("cli") != {"package": CLI_PACKAGE, "version": CLI_VERSION}:
        raise ValueError(f"cli must pin {CLI_PACKAGE}@{CLI_VERSION}")

    collection_id = config.get("collection_id")
    if not isinstance(collection_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]+", collection_id):
        raise ValueError("collection_id must contain lowercase letters, digits, and hyphens")

    queries = _as_list(config.get("queries"), "queries")
    if not queries or not all(isinstance(query, str) and query.strip() for query in queries):
        raise ValueError("queries must contain non-empty strings")
    if len(set(queries)) != len(queries):
        raise ValueError("queries must be unique")

    request = _as_mapping(config.get("request"), "request")
    pagination = _as_mapping(request.get("pagination"), "request.pagination")
    limit = pagination.get("limit")
    max_pages = pagination.get("max_pages")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValueError("request.pagination.limit must be an integer from 1 through 50")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages < 1:
        raise ValueError("request.pagination.max_pages must be a positive integer")

    retry = _as_mapping(config.get("retry"), "retry")
    for field in ("max_attempts", "timeout_seconds"):
        value = retry.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"retry.{field} must be a positive integer")
    for field in ("backoff_seconds", "inter_request_seconds"):
        value = retry.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            raise ValueError(f"retry.{field} must be non-negative")

    window = _as_mapping(config.get("collection_window_utc"), "collection_window_utc")
    start = _parse_utc(window.get("start"), "collection_window_utc.start")
    end = _parse_utc(window.get("end"), "collection_window_utc.end")
    if start >= end:
        raise ValueError("collection_window_utc.start must precede end")

    versions = _as_list(config.get("accepted_protocol_versions"), "accepted_protocol_versions")
    if not versions or not all(isinstance(version, str) and version for version in versions):
        raise ValueError("accepted_protocol_versions must contain strings")
    return config


def build_search_input(config: Mapping[str, object], query: str, cursor: str | None) -> dict:
    request = _as_mapping(config["request"], "request")
    pagination = _as_mapping(request["pagination"], "request.pagination")
    payload = {
        "query": query,
        "context": request.get("context", {}),
        "filters": request.get("filters", {}),
        "view": request.get("server_view", "offer"),
        "pagination": {"limit": pagination["limit"]},
    }
    if cursor is not None:
        payload["pagination"]["cursor"] = cursor
    return payload


def protocol_version(envelope: Mapping[str, object]) -> str | None:
    ucp = envelope.get("ucp")
    if not isinstance(ucp, Mapping):
        return None
    version = ucp.get("version")
    return version if isinstance(version, str) else None


def next_cursor(envelope: Mapping[str, object]) -> str | None:
    result = _as_mapping(envelope.get("result"), "response.result")
    pagination = result.get("pagination")
    if pagination is None:
        return None
    pagination = _as_mapping(pagination, "response.result.pagination")
    has_next_page = pagination.get("has_next_page", False)
    if not isinstance(has_next_page, bool):
        raise ValueError("response.result.pagination.has_next_page must be boolean")
    if not has_next_page:
        return None
    cursor = pagination.get("cursor")
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("paginated response has no next cursor")
    return cursor


def normalize_page(
    envelope: Mapping[str, object],
    *,
    collection_id: str,
    query: str,
    query_index: int,
    page_index: int,
    received_at: str,
    source_sha256: str,
) -> list[dict[str, object]]:
    result = _as_mapping(envelope.get("result"), "response.result")
    products = _as_list(result.get("products"), "response.result.products")
    rows: list[dict[str, object]] = []
    for product_index, product_value in enumerate(products):
        product = _as_mapping(product_value, f"response.result.products[{product_index}]")
        variants = _as_list(
            product.get("variants", []),
            f"response.result.products[{product_index}].variants",
        )
        for variant_index, variant_value in enumerate(variants):
            variant = _as_mapping(
                variant_value,
                f"response.result.products[{product_index}].variants[{variant_index}]",
            )
            seller_value = variant.get("seller", {})
            seller = seller_value if isinstance(seller_value, Mapping) else {}
            price_value = variant.get("price", {})
            price = price_value if isinstance(price_value, Mapping) else {}
            availability_value = variant.get("availability", {})
            availability = (
                availability_value if isinstance(availability_value, Mapping) else {}
            )
            requires_value = variant.get("requires", {})
            requires = requires_value if isinstance(requires_value, Mapping) else {}

            seller_domain = normalize_seller_domain(seller.get("domain"))
            amount = price.get("amount")
            currency = price.get("currency")
            reasons: list[str] = []
            if not isinstance(product.get("id"), str) or not product.get("id"):
                reasons.append("missing_product_id")
            if not isinstance(variant.get("id"), str) or not variant.get("id"):
                reasons.append("missing_variant_id")
            if seller_domain is None:
                reasons.append("missing_seller_domain")
            if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
                reasons.append("invalid_price_amount")
            if not isinstance(currency, str) or _CURRENCY.fullmatch(currency) is None:
                reasons.append("invalid_price_currency")
            if availability.get("available") is False:
                reasons.append("unavailable")
            if requires.get("components") is True:
                reasons.append("requires_components")

            rows.append(
                {
                    "schema_version": OFFER_SCHEMA_VERSION,
                    "collection_id": collection_id,
                    "source": {
                        "query": query,
                        "query_index": query_index,
                        "page_index": page_index,
                        "product_index": product_index,
                        "variant_index": variant_index,
                        "received_at": received_at,
                        "response_sha256": source_sha256,
                    },
                    "product": {
                        "id": product.get("id"),
                        "title": product.get("title"),
                        "url": product.get("url"),
                        "categories": product.get("categories"),
                        "options": product.get("options"),
                        "selected": product.get("selected"),
                    },
                    "variant": {
                        "id": variant.get("id"),
                        "title": variant.get("title"),
                        "inputs": variant.get("inputs"),
                        "options": variant.get("options"),
                        "condition": variant.get("condition"),
                        "url": variant.get("url"),
                        "checkout_url": variant.get("checkout_url"),
                    },
                    "seller": {
                        "id": seller.get("id"),
                        "name": seller.get("name"),
                        "domain": seller_domain,
                        "url": seller.get("url"),
                    },
                    "price": {"amount": amount, "currency": currency},
                    "availability": dict(availability),
                    "requires": dict(requires),
                    "analysis_eligible": not reasons,
                    "exclusion_reasons": reasons,
                }
            )
    return rows


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:48] or "query"


def _recovered_resource_usage(raw: bytes) -> dict[str, object]:
    return {
        "telemetry_status": "unobserved_before_checkpointing",
        "elapsed_ms": None,
        "catalog_search_call_attempts": None,
        "response_bytes": len(raw),
        "attempts": [],
        "token_usage": {
            "observed": False,
            "value": None,
            "reason": "not_exposed_by_ucp_catalog_response",
        },
        "api_billing_minor": {
            "observed": False,
            "value": None,
            "reason": "not_exposed_by_ucp_catalog_response",
        },
    }


def _run_page(
    payload: Mapping[str, object],
    *,
    environment: Mapping[str, str],
    max_attempts: int,
    timeout_seconds: int,
    backoff_seconds: float,
) -> tuple[bytes, dict[str, object]]:
    command = (*CLI_COMMAND, "catalog", "search", "--input", json.dumps(payload))
    last_error: Exception | None = None
    attempts: list[dict[str, object]] = []
    request_started = time.perf_counter()
    for attempt_index in range(max_attempts):
        attempt_started_at = _timestamp()
        attempt_started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                env=environment,
                timeout=timeout_seconds,
            )
            json.loads(completed.stdout)
            attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "started_at": attempt_started_at,
                    "elapsed_ms": round((time.perf_counter() - attempt_started) * 1000, 3),
                    "outcome": "success",
                    "response_bytes": len(completed.stdout),
                }
            )
            return completed.stdout, {
                "telemetry_status": "observed",
                "elapsed_ms": round((time.perf_counter() - request_started) * 1000, 3),
                "catalog_search_call_attempts": len(attempts),
                "response_bytes": len(completed.stdout),
                "attempts": attempts,
                "token_usage": {
                    "observed": False,
                    "value": None,
                    "reason": "not_exposed_by_ucp_catalog_response",
                },
                "api_billing_minor": {
                    "observed": False,
                    "value": None,
                    "reason": "not_exposed_by_ucp_catalog_response",
                },
            }
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
        ) as error:
            last_error = error
            response = getattr(error, "stdout", None)
            attempts.append(
                {
                    "attempt": attempt_index + 1,
                    "started_at": attempt_started_at,
                    "elapsed_ms": round((time.perf_counter() - attempt_started) * 1000, 3),
                    "outcome": type(error).__name__,
                    "response_bytes": len(response) if isinstance(response, bytes) else 0,
                }
            )
            if attempt_index + 1 < max_attempts:
                time.sleep(backoff_seconds * (2**attempt_index))
    raise RuntimeError(f"catalog request failed after {max_attempts} attempts: {last_error}")


def collect(config_path: Path, output_dir: Path, *, resume: bool = False) -> dict[str, object]:
    config_bytes = config_path.read_bytes()
    config = load_config(config_path)
    window = _as_mapping(config["collection_window_utc"], "collection_window_utc")
    started = datetime.now(UTC)
    window_start = _parse_utc(window["start"], "collection_window_utc.start")
    window_end = _parse_utc(window["end"], "collection_window_utc.end")
    if not window_start <= started <= window_end:
        raise RuntimeError("current time is outside the frozen collection window")
    if resume:
        if not output_dir.is_dir():
            raise RuntimeError("resume requires an existing output directory")
    else:
        output_dir.mkdir(parents=True, exist_ok=False)

    retry = _as_mapping(config["retry"], "retry")
    pagination = _as_mapping(
        _as_mapping(config["request"], "request")["pagination"],
        "request.pagination",
    )
    accepted_versions = set(config["accepted_protocol_versions"])
    pages: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="global-catalog-ucp-home-") as ucp_home:
        environment = {**os.environ, "UCP_HOME": ucp_home}
        version = subprocess.run(
            (*CLI_COMMAND, "--version"),
            check=True,
            capture_output=True,
            env=environment,
            text=True,
            timeout=int(retry["timeout_seconds"]),
        ).stdout.strip()
        if f"ucp {CLI_VERSION}" not in version:
            raise RuntimeError(f"unexpected CLI version output: {version}")

        for query_index, query_value in enumerate(config["queries"]):
            query = str(query_value)
            cursor: str | None = None
            for page_index in range(int(pagination["max_pages"])):
                if datetime.now(UTC) > window_end:
                    raise RuntimeError("collection exceeded the frozen collection window")
                payload = build_search_input(config, query, cursor)
                relative_path = Path("raw") / (
                    f"{query_index:03d}-{_slug(query)}-page-{page_index:03d}.json"
                )
                raw_path = output_dir / relative_path
                checkpoint_path = output_dir / "pages" / f"{relative_path.stem}.json"
                if raw_path.is_file():
                    if not resume:
                        raise RuntimeError(f"unexpected existing response page: {raw_path}")
                    raw = raw_path.read_bytes()
                    received_at = datetime.fromtimestamp(
                        raw_path.stat().st_mtime, UTC
                    ).isoformat(timespec="seconds").replace("+00:00", "Z")
                    resource_usage = _recovered_resource_usage(raw)
                    if checkpoint_path.is_file():
                        checkpoint = _as_mapping(
                            json.loads(checkpoint_path.read_text(encoding="utf-8")),
                            "page checkpoint",
                        )
                        if checkpoint.get("raw_sha256") != _sha256(raw):
                            raise RuntimeError(f"checkpoint hash mismatch: {raw_path}")
                        received_at = str(checkpoint["received_at"])
                        resource_usage = dict(
                            _as_mapping(checkpoint["resource_usage"], "resource_usage")
                        )
                else:
                    raw, resource_usage = _run_page(
                        payload,
                        environment=environment,
                        max_attempts=int(retry["max_attempts"]),
                        timeout_seconds=int(retry["timeout_seconds"]),
                        backoff_seconds=float(retry["backoff_seconds"]),
                    )
                    received_at = _timestamp()
                    _write_atomic(raw_path, raw)
                digest = _sha256(raw)
                envelope = _as_mapping(json.loads(raw), "response")
                observed_version = protocol_version(envelope)
                if observed_version not in accepted_versions:
                    raise RuntimeError(f"unexpected UCP protocol version: {observed_version}")
                rows.extend(
                    normalize_page(
                        envelope,
                        collection_id=str(config["collection_id"]),
                        query=query,
                        query_index=query_index,
                        page_index=page_index,
                        received_at=received_at,
                        source_sha256=digest,
                    )
                )
                page_record = {
                    "query": query,
                    "query_index": query_index,
                    "page_index": page_index,
                    "received_at": received_at,
                    "request": payload,
                    "raw_path": relative_path.as_posix(),
                    "raw_sha256": digest,
                    "resource_usage": resource_usage,
                }
                pages.append(page_record)
                if not checkpoint_path.is_file():
                    _write_atomic(checkpoint_path, _canonical_bytes(page_record))
                cursor = next_cursor(envelope)
                if cursor is None:
                    break
                time.sleep(float(retry["inter_request_seconds"]))

    offers = b"".join(_canonical_bytes(row) for row in rows)
    _write_atomic(output_dir / "offers.jsonl", offers)
    result = {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "collection_id": config["collection_id"],
        "started_at": started.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "completed_at": _timestamp(),
        "config_path": config_path.as_posix(),
        "config_sha256": _sha256(config_bytes),
        "cli": {"command": list(CLI_COMMAND), "version_output": version},
        "pages": pages,
        "page_count": len(pages),
        "offer_row_count": len(rows),
        "eligible_offer_row_count": sum(bool(row["analysis_eligible"]) for row in rows),
        "resource_usage": {
            "elapsed_ms": {
                "observed_page_count": sum(
                    page["resource_usage"]["elapsed_ms"] is not None for page in pages
                ),
                "unobserved_page_count": sum(
                    page["resource_usage"]["elapsed_ms"] is None for page in pages
                ),
                "observed_total": round(
                    sum(
                        float(page["resource_usage"]["elapsed_ms"])
                        for page in pages
                        if page["resource_usage"]["elapsed_ms"] is not None
                    ),
                    3,
                ),
            },
            "catalog_search_call_attempts": {
                "observed_page_count": sum(
                    page["resource_usage"]["catalog_search_call_attempts"] is not None
                    for page in pages
                ),
                "unobserved_page_count": sum(
                    page["resource_usage"]["catalog_search_call_attempts"] is None
                    for page in pages
                ),
                "observed_total": sum(
                    int(page["resource_usage"]["catalog_search_call_attempts"])
                    for page in pages
                    if page["resource_usage"]["catalog_search_call_attempts"] is not None
                ),
            },
            "response_bytes": sum(
                int(page["resource_usage"]["response_bytes"]) for page in pages
            ),
            "token_usage": {
                "observed": False,
                "value": None,
                "reason": "not_exposed_by_ucp_catalog_response",
            },
            "api_billing_minor": {
                "observed": False,
                "value": None,
                "reason": "not_exposed_by_ucp_catalog_response",
            },
        },
        "offers_path": "offers.jsonl",
        "offers_sha256": _sha256(offers),
    }
    _write_atomic(output_dir / "collection.json", _canonical_bytes(result))
    return result


def recover_complete_prefix(config_path: Path, output_dir: Path) -> dict[str, object]:
    """Materialize only terminally paginated raw query prefixes without network access."""
    config_bytes = config_path.read_bytes()
    config = load_config(config_path)
    raw_dir = output_dir / "raw"
    if not raw_dir.is_dir():
        raise RuntimeError("recovery requires an existing raw response directory")

    accepted_versions = set(config["accepted_protocol_versions"])
    pages: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    completed_queries: list[str] = []
    timestamps: list[datetime] = []
    for query_index, query_value in enumerate(config["queries"]):
        query = str(query_value)
        page_paths = sorted(raw_dir.glob(f"{query_index:03d}-{_slug(query)}-page-*.json"))
        if not page_paths:
            break
        page_start = len(pages)
        row_start = len(rows)
        timestamp_start = len(timestamps)
        cursor: str | None = None
        terminal = False
        for page_index, raw_path in enumerate(page_paths):
            expected_name = f"{query_index:03d}-{_slug(query)}-page-{page_index:03d}.json"
            if raw_path.name != expected_name:
                raise RuntimeError(f"raw pages are not contiguous for query {query!r}")
            raw = raw_path.read_bytes()
            envelope = _as_mapping(json.loads(raw), "response")
            observed_version = protocol_version(envelope)
            if observed_version not in accepted_versions:
                raise RuntimeError(f"unexpected UCP protocol version: {observed_version}")
            received_at = datetime.fromtimestamp(
                raw_path.stat().st_mtime, UTC
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            timestamps.append(_parse_utc(received_at, "raw page timestamp"))
            rows.extend(
                normalize_page(
                    envelope,
                    collection_id=str(config["collection_id"]),
                    query=query,
                    query_index=query_index,
                    page_index=page_index,
                    received_at=received_at,
                    source_sha256=_sha256(raw),
                )
            )
            payload = build_search_input(config, query, cursor)
            pages.append(
                {
                    "query": query,
                    "query_index": query_index,
                    "page_index": page_index,
                    "received_at": received_at,
                    "request": payload,
                    "raw_path": raw_path.relative_to(output_dir).as_posix(),
                    "raw_sha256": _sha256(raw),
                    "resource_usage": _recovered_resource_usage(raw),
                }
            )
            cursor = next_cursor(envelope)
            if cursor is None:
                terminal = True
                break
        if not terminal:
            del pages[page_start:]
            del rows[row_start:]
            del timestamps[timestamp_start:]
            break
        completed_queries.append(query)

    if not completed_queries:
        raise RuntimeError("raw responses contain no complete query prefix")
    offers = b"".join(_canonical_bytes(row) for row in rows)
    _write_atomic(output_dir / "offers.jsonl", offers)
    completed_at = max(timestamps).isoformat(timespec="seconds").replace("+00:00", "Z")
    started_at = min(timestamps).isoformat(timespec="seconds").replace("+00:00", "Z")
    result = {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "collection_id": config["collection_id"],
        "collection_status": "recovered_complete_query_prefix",
        "started_at": started_at,
        "completed_at": completed_at,
        "config_path": config_path.as_posix(),
        "config_sha256": _sha256(config_bytes),
        "cli": {"command": list(CLI_COMMAND), "version_output": None},
        "planned_query_count": len(config["queries"]),
        "completed_query_count": len(completed_queries),
        "completed_queries": completed_queries,
        "pages": pages,
        "page_count": len(pages),
        "offer_row_count": len(rows),
        "eligible_offer_row_count": sum(bool(row["analysis_eligible"]) for row in rows),
        "resource_usage": {
            "elapsed_ms": {
                "observed_page_count": 0,
                "unobserved_page_count": len(pages),
                "observed_total": 0,
            },
            "catalog_search_call_attempts": {
                "observed_page_count": 0,
                "unobserved_page_count": len(pages),
                "observed_total": 0,
            },
            "response_bytes": sum(int(page["resource_usage"]["response_bytes"]) for page in pages),
            "token_usage": {
                "observed": False,
                "value": None,
                "reason": "not_exposed_by_ucp_catalog_response",
            },
            "api_billing_minor": {
                "observed": False,
                "value": None,
                "reason": "not_exposed_by_ucp_catalog_response",
            },
        },
        "offers_path": "offers.jsonl",
        "offers_sha256": _sha256(offers),
    }
    _write_atomic(output_dir / "collection.json", _canonical_bytes(result))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--recover-complete-prefix", action="store_true")
    args = parser.parse_args(argv)
    if args.resume and args.recover_complete_prefix:
        raise ValueError("--resume and --recover-complete-prefix cannot be combined")
    if args.recover_complete_prefix:
        result = recover_complete_prefix(args.config, args.output_dir)
    else:
        result = collect(args.config, args.output_dir, resume=args.resume)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_global_catalog.py"
SPEC = importlib.util.spec_from_file_location("collect_global_catalog", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
collect_global_catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collect_global_catalog)


def _fixture() -> dict[str, object]:
    path = ROOT / "tests" / "fixtures" / "global-catalog-search-page.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_registered_collection_config_is_valid_and_price_independent() -> None:
    config = collect_global_catalog.load_config(
        ROOT / "research" / "global-catalog-collection.json"
    )

    assert config["collection_id"] == "shopify-global-catalog-2026-09-17"
    assert config["cli"] == {"package": "@shopify/ucp-cli", "version": "0.9.0"}
    assert config["accepted_protocol_versions"] == ["2026-08-25"]
    assert len(config["queries"]) == 48
    assert all("$" not in query for query in config["queries"])
    assert config["request"]["pagination"] == {"limit": 50, "max_pages": 4}


def test_deep_collection_is_new_and_capped_at_one_thousand_results_per_query() -> None:
    config = collect_global_catalog.load_config(
        ROOT / "research" / "global-catalog-collection-2026-09-18-deep.json"
    )

    assert config["collection_id"] == "shopify-global-catalog-2026-09-18-deep"
    assert config["request"]["pagination"] == {"limit": 50, "max_pages": 20}
    assert len(config["queries"]) == 48
    assert all("$" not in query for query in config["queries"])


def test_fixture_normalizes_every_variant_with_provenance() -> None:
    envelope = _fixture()
    raw = json.dumps(envelope).encode()
    rows = collect_global_catalog.normalize_page(
        envelope,
        collection_id="fixture-collection",
        query="running shoes",
        query_index=4,
        page_index=2,
        received_at="2026-09-17T04:30:00Z",
        source_sha256=collect_global_catalog._sha256(raw),
    )

    assert len(rows) == 3
    assert rows[0]["schema_version"] == 1
    assert rows[0]["product"]["id"] == "gid://shopify/p/example-shoe"
    assert rows[0]["product"]["selected"] == [
        {"name": "Shoe size", "label": "us 10"}
    ]
    assert rows[0]["seller"]["domain"] == "alpha-running.myshopify.com"
    assert rows[0]["source"] == {
        "query": "running shoes",
        "query_index": 4,
        "page_index": 2,
        "product_index": 0,
        "variant_index": 0,
        "received_at": "2026-09-17T04:30:00Z",
        "response_sha256": collect_global_catalog._sha256(raw),
    }
    assert rows[0]["analysis_eligible"] is True
    assert rows[0]["exclusion_reasons"] == []
    assert rows[1]["analysis_eligible"] is False
    assert rows[1]["exclusion_reasons"] == ["unavailable"]
    assert rows[2]["price"] == {"amount": 11999, "currency": "EUR"}
    assert rows[2]["analysis_eligible"] is True


def test_fixture_pagination_uses_server_cursor() -> None:
    assert collect_global_catalog.next_cursor(_fixture()) == "next-page-token"


def test_pagination_rejects_missing_cursor() -> None:
    envelope = _fixture()
    del envelope["result"]["pagination"]["cursor"]
    with pytest.raises(ValueError, match="no next cursor"):
        collect_global_catalog.next_cursor(envelope)


def test_search_input_does_not_reuse_server_ranking() -> None:
    config = {
        "request": {
            "context": {"address_country": "US", "currency": "USD"},
            "filters": {"available": True},
            "server_view": "offer",
            "pagination": {"limit": 50, "max_pages": 4},
        }
    }
    payload = collect_global_catalog.build_search_input(config, "running shoes", "cursor-2")
    assert payload == {
        "query": "running shoes",
        "context": {"address_country": "US", "currency": "USD"},
        "filters": {"available": True},
        "view": "offer",
        "pagination": {"limit": 50, "cursor": "cursor-2"},
    }


def test_cli_command_is_exactly_pinned() -> None:
    assert collect_global_catalog.CLI_COMMAND == (
        "npx",
        "--yes",
        "--package",
        "@shopify/ucp-cli@0.9.0",
        "ucp",
    )


def test_page_request_records_resource_observability(monkeypatch: pytest.MonkeyPatch) -> None:
    def completed(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=b"{}", stderr=b"")

    monkeypatch.setattr(collect_global_catalog.subprocess, "run", completed)
    raw, usage = collect_global_catalog._run_page(
        {"query": "shoes"},
        environment={},
        max_attempts=1,
        timeout_seconds=5,
        backoff_seconds=0,
    )

    assert raw == b"{}"
    assert usage["catalog_search_call_attempts"] == 1
    assert usage["response_bytes"] == 2
    assert usage["attempts"][0]["outcome"] == "success"
    assert usage["token_usage"]["observed"] is False
    assert usage["api_billing_minor"]["value"] is None


def test_resume_replays_existing_page_without_catalog_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    now = datetime.now(UTC)
    config = {
        "collection_id": "resume-fixture",
        "accepted_protocol_versions": ["2026-08-25"],
        "collection_window_utc": {
            "start": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "end": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        },
        "request": {
            "context": {},
            "filters": {},
            "server_view": "offer",
            "pagination": {"limit": 50, "max_pages": 1},
        },
        "retry": {
            "max_attempts": 1,
            "timeout_seconds": 5,
            "backoff_seconds": 0,
            "inter_request_seconds": 0,
        },
        "queries": ["running shoes"],
    }
    output = tmp_path / "partial"
    raw_path = output / "raw" / "000-running-shoes-page-000.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(json.dumps(_fixture()), encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(collect_global_catalog, "load_config", lambda path: config)
    monkeypatch.setattr(
        collect_global_catalog.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ucp 0.9.0", stderr=""
        ),
    )

    def unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("resume must not request an existing page")

    monkeypatch.setattr(collect_global_catalog, "_run_page", unexpected_call)
    result = collect_global_catalog.collect(config_path, output, resume=True)

    assert result["page_count"] == 1
    assert result["resource_usage"]["elapsed_ms"]["unobserved_page_count"] == 1
    assert (output / "pages" / "000-running-shoes-page-000.json").is_file()


def test_recovery_uses_only_a_terminal_raw_query_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = {
        "collection_id": "recovery-fixture",
        "accepted_protocol_versions": ["2026-08-25"],
        "collection_window_utc": {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        },
        "request": {
            "context": {},
            "filters": {},
            "server_view": "offer",
            "pagination": {"limit": 50, "max_pages": 2},
        },
        "retry": {
            "max_attempts": 1,
            "timeout_seconds": 5,
            "backoff_seconds": 0,
            "inter_request_seconds": 0,
        },
        "queries": ["running shoes", "hiking boots"],
    }
    output = tmp_path / "partial"
    raw = output / "raw"
    raw.mkdir(parents=True)
    terminal = _fixture()
    terminal["result"]["pagination"] = {"has_next_page": False}
    (raw / "000-running-shoes-page-000.json").write_text(json.dumps(terminal), encoding="utf-8")
    incomplete = _fixture()
    incomplete["result"]["pagination"] = {"has_next_page": True, "cursor": "next"}
    (raw / "001-hiking-boots-page-000.json").write_text(json.dumps(incomplete), encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(collect_global_catalog, "load_config", lambda path: config)

    result = collect_global_catalog.recover_complete_prefix(config_path, output)

    assert result["collection_status"] == "recovered_complete_query_prefix"
    assert result["completed_queries"] == ["running shoes"]
    assert result["page_count"] == 1
    assert (output / "offers.jsonl").is_file()
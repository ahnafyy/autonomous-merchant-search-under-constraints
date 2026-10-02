from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_global_catalog.py"
SPEC = importlib.util.spec_from_file_location("analyze_global_catalog", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
analyze_global_catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze_global_catalog)


def test_analysis_rejects_offer_file_that_does_not_match_manifest(tmp_path: Path) -> None:
    collection_dir = tmp_path / "collection"
    collection_dir.mkdir()
    (collection_dir / "offers.jsonl").write_text("{}\n", encoding="utf-8")
    (collection_dir / "collection.json").write_text(
        json.dumps({"offers_sha256": "not-the-file-hash"}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="manifest hash"):
        analyze_global_catalog.analyze(
            collection_dir, ROOT / "research" / "hidden-card-analysis.json"
        )


def test_analysis_reports_insufficient_product_decks(tmp_path: Path) -> None:
    collection_dir = tmp_path / "collection"
    collection_dir.mkdir()
    row = {
        "analysis_eligible": True,
        "exclusion_reasons": [],
        "product": {"id": "gid://shopify/p/singleton", "title": "Singleton"},
        "variant": {
            "id": "gid://shopify/ProductVariant/1",
            "title": "Default",
        },
        "seller": {"domain": "seller.example"},
        "price": {"amount": 1000, "currency": "USD"},
    }
    offers = (json.dumps(row) + "\n").encode()
    (collection_dir / "offers.jsonl").write_bytes(offers)
    (collection_dir / "collection.json").write_text(
        json.dumps(
            {
                "collection_id": "test-collection",
                "offers_sha256": hashlib.sha256(offers).hexdigest(),
                "offer_row_count": 1,
                "eligible_offer_row_count": 1,
            }
        ),
        encoding="utf-8",
    )

    result = analyze_global_catalog.analyze(
        collection_dir, ROOT / "research" / "hidden-card-analysis.json"
    )

    assert result["analysis"] == {
        "status": "insufficient_eligible_products",
        "random_seed": 20260723,
        "minimum_required_product_decks": 4,
        "cost_rate_card": {
            "path": "research/cost-rate-card-2026-09.json",
            "as_of": "2026-09-28",
            "sha256": result["analysis"]["cost_rate_card"]["sha256"],
        },
    }
    assert result["deck_build"]["product_deck_count"] == 0
    assert result["deck_build"]["deck_audit"] == []
    assert result["deck_build"]["product_identity"]["strategy"] == (
        "exact_normalized_model_title_or_catalog_product_option"
    )
    assert result["deck_build"]["exclusion_counts"] == {
        "insufficient_independent_sellers": 1
    }
    assert result["study"] is None
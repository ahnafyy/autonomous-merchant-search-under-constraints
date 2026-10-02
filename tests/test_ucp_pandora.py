from __future__ import annotations

import gzip
import json
from pathlib import Path

from autonomous_shopping_optimizer.ucp_pandora import (
    build_ucp_panel_decks,
    build_ucp_panel_series,
)


def test_build_ucp_panel_decks_uses_present_usd_same_sku_offers(tmp_path: Path) -> None:
    path = tmp_path / "panel.jsonl.gz"
    rows = [
        {
            "sku": "sku-1", "domain": "a.example", "present": True,
            "price_amount": 100, "price_currency": "USD",
        },
        {
            "sku": "sku-1", "domain": "b.example", "present": True,
            "price_amount": 90, "price_currency": "USD",
        },
        {
            "sku": "sku-1", "domain": "c.example", "present": True,
            "price_amount": 110, "price_currency": "USD",
        },
        {
            "sku": "sku-1", "domain": "d.example", "present": False,
            "price_amount": None, "price_currency": None,
        },
        {
            "sku": "sku-2", "domain": "e.example", "present": True,
            "price_amount": 50, "price_currency": "USD",
        },
    ]
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    result = build_ucp_panel_decks(path, observation_date="2026-09-03")

    assert result.input_rows == 5
    assert result.exclusion_counts == {"insufficient_sellers": 1, "not_present": 1}
    assert len(result.decks) == 1
    assert result.decks[0].product_id == "sku-1"
    assert result.decks[0].deck_id == "sku-1@2026-09-03::ucp-panel"
    assert [card.price_minor for card in result.decks[0].cards] == [100, 90, 110]


def test_panel_series_keeps_sku_clustered_but_dates_distinct(tmp_path: Path) -> None:
    for observation_date in ("2026-09-03", "2026-09-04"):
        path = tmp_path / f"panel-observations-{observation_date}.jsonl.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for domain, amount in (("a.example", 100), ("b.example", 90), ("c.example", 110)):
                handle.write(
                    json.dumps(
                        {
                            "sku": "sku-1",
                            "domain": domain,
                            "present": True,
                            "price_amount": amount,
                            "price_currency": "USD",
                        }
                    )
                    + "\n"
                )

    decks, counts = build_ucp_panel_series(
        tmp_path, ("2026-09-03", "2026-09-04")
    )

    assert counts == {"2026-09-03": 1, "2026-09-04": 1}
    assert {deck.product_id for deck in decks} == {"sku-1"}
    assert {deck.deck_id for deck in decks} == {
        "sku-1@2026-09-03::ucp-panel",
        "sku-1@2026-09-04::ucp-panel",
    }
#!/usr/bin/env python3
"""Bucket UCP scan candidates by transport support and a domain-name category guess.

This groups candidates to make manual same-SKU curation tractable; it does not
establish that any two merchants sell the same SKU. Category membership is a
heuristic guess from domain-name keywords only. Confirming that two or more
merchants carry an identical, comparable SKU requires either prior product
knowledge or a live per-merchant catalog lookup against a specific target
product -- and any live lookup against a merchant is out of scope until that
merchant's `permission_status` is confirmed `"verified"` (see data/ucp/README.md).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Ordered so the first matching category wins for domains that match more than
# one keyword group (e.g. "petcosmetics.example" would match "beauty" first).
CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("hats_caps", ("hat", "cap", "milliner")),
    ("footwear_sneakers", ("shoe", "sneaker", "boot", "sole", "kicks", "footwear")),
    ("socks", ("sock",)),
    ("eyewear", ("sunglass", "eyewear", "optic", "glasses")),
    ("bags_luggage", ("luggage", "backpack", "bag", "pack")),
    ("jewelry_watches", ("jewel", "watch", "ring")),
    ("beauty_cosmetics", ("beauty", "cosmetic", "skin", "hair", "makeup", "cream")),
    ("coffee_beverage", ("coffee", "tea", "brew", "roast", "drink")),
    ("food_snacks", ("food", "snack", "chocolate", "candy", "sweet", "cookie")),
    ("pet", ("pet", "dog", "cat", "paw", "hound")),
    ("kids_baby", ("baby", "kid", "toddler", "toy")),
    ("books_media", ("book", "read", "magazine")),
    ("fitness_supplements", ("fitness", "gym", "protein", "supplement", "muscle", "strength")),
    ("outdoor_bike_ski", ("bike", "cycl", "ski", "outdoor", "camp", "trail")),
    ("electronics_accessories", ("phone", "case", "electronic", "tech", "gadget", "charger")),
    ("home_decor", ("home", "decor", "furniture", "rug", "candle")),
    ("apparel_general", ("wear", "apparel", "cloth", "fashion", "style", "threads", "outfit")),
]

_WORD_SPLIT = re.compile(r"[^a-z]+")


def _domain_tokens(domain: str) -> set[str]:
    label = domain.split(".", 1)[0].lower()
    return set(filter(None, _WORD_SPLIT.split(label))) | {label}


def _categorize(domain: str) -> str:
    tokens = _domain_tokens(domain)
    haystack = domain.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in haystack or any(keyword in token for token in tokens):
                return category
    return "uncategorized"


def load_candidates(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload["endpoints"])


def select_mcp_candidates(
    endpoints: list[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        endpoint
        for endpoint in endpoints
        if "mcp" in (endpoint.get("scan_transports") or [])
    ]


def group_by_category(
    endpoints: list[dict[str, object]],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for endpoint in endpoints:
        domain = str(endpoint["endpoint_id"])
        grouped[_categorize(domain)].append(domain)
    return {
        category: sorted(domains) for category, domains in sorted(grouped.items())
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "candidates_path", type=Path, help="Path to a candidate inventory JSON"
    )
    parser.add_argument(
        "output_path", type=Path, help="Path to write the category grouping JSON"
    )
    args = parser.parse_args(argv)

    endpoints = load_candidates(args.candidates_path)
    mcp_endpoints = select_mcp_candidates(endpoints)
    grouped = group_by_category(mcp_endpoints)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(grouped, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"total candidates: {len(endpoints)}")
    print(f"mcp-transport candidates: {len(mcp_endpoints)}")
    print(f"wrote category grouping: {args.output_path}")
    print()
    for category, domains in sorted(grouped.items(), key=lambda kv: -len(kv[1])):
        print(f"{category}: {len(domains)}")
    print()
    print(
        "Category membership is a domain-name heuristic, not a confirmed catalog "
        "match. Same-SKU overlap between any two merchants is not established by "
        "this scan and must be confirmed before use."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

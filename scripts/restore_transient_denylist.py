#!/usr/bin/env python3
"""Restore domains falsely denylisted by a documented DNS-resolution outage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DNS_FAILURE_MARKER = "nodename nor servname"


def dns_failed_domains(manifest_path: Path) -> set[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        domain
        for domain, status in manifest.get("domain_status", {}).items()
        if DNS_FAILURE_MARKER in status
    }


def restore_domains(denylist_path: Path, domains: set[str]) -> list[str]:
    lines = denylist_path.read_text(encoding="utf-8").splitlines()
    removed: list[str] = []
    retained: list[str] = []
    for line in lines:
        domain = line.split("#", 1)[0].strip()
        if domain in domains and DNS_FAILURE_MARKER in line:
            removed.append(domain)
        else:
            retained.append(line)

    temporary = denylist_path.with_suffix(denylist_path.suffix + ".tmp")
    temporary.write_text("\n".join(retained) + "\n", encoding="utf-8")
    temporary.replace(denylist_path)
    return sorted(removed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Failed panel-run manifest")
    parser.add_argument(
        "--denylist",
        type=Path,
        default=Path("data/ucp/crawler-denylist.txt"),
        help="Crawler denylist to repair",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    domains = dns_failed_domains(args.manifest)
    if args.dry_run:
        print(f"would restore {len(domains)} domains from {args.manifest}")
        return 0

    removed = restore_domains(args.denylist, domains)
    print(f"restored {len(removed)} DNS-failure entries from {args.denylist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
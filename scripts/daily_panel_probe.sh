#!/bin/bash
# Daily panel probe. Scheduled by launchd; safe to run by hand.
#
# Uses a deep page cap because only panel merchants are contacted: a truncated
# merchant cannot distinguish "offer gone" from "offer beyond the page cap", so
# paying for depth here directly increases how many offers are judgeable.
set -euo pipefail

REPO="/Users/ahnafy/appdev/repos/autonomous-merchant-search-under-constraints"
cd "$REPO"

PYTHON="$REPO/.venv/bin/python"
TODAY="$(date +%Y-%m-%d)"
PANEL="$(ls -1 data/ucp/panel-*.jsonl.gz | grep -v observations | sort | tail -1)"

echo "=== panel probe $TODAY ==="
echo "panel: $PANEL"

"$PYTHON" scripts/probe_panel.py \
  --date "$TODAY" \
  --panel "$PANEL" \
  --max-pages 40 \
  --page-size 50 \
  --workers 10 \
  --delay-seconds 1.0

# Needs two or more observation dates before it reports anything.
"$PYTHON" scripts/offer_survival.py || true

echo "=== done $(date) ==="

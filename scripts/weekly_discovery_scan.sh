#!/bin/bash
# Weekly full discovery scan across every candidate merchant, then refresh the panel.
#
# The daily probe only re-checks products already known to be multi-seller, so it
# cannot find new ones. This does, and takes about 45 minutes.
set -euo pipefail

REPO="/Users/ahnafy/appdev/repos/autonomous-merchant-search-under-constraints"
cd "$REPO"

PYTHON="$REPO/.venv/bin/python"
TODAY="$(date +%Y-%m-%d)"

echo "=== weekly discovery scan $TODAY ==="

"$PYTHON" scripts/deep_isbn_scan.py \
  --date "$TODAY" \
  --include-candidates \
  --max-pages 12 \
  --page-size 50 \
  --workers 15 \
  --delay-seconds 1.0

"$PYTHON" scripts/overlap_report.py --date "$TODAY"
"$PYTHON" scripts/extract_panel.py --date "$TODAY"

# The raw snapshot is hundreds of megabytes and is a discovery artifact, not
# evidence; the panel extracted from it is what the study replays.
rm -f "data/ucp/deep-scan-rows-${TODAY}.jsonl"

echo "=== done $(date) ==="

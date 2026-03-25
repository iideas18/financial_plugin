#!/usr/bin/env bash
# check-cache.sh — Check if Phase 1 research cache is still valid.
#
# Usage:
#   bash scripts/check-cache.sh <source_dir> <docs_dir>
#
# Exit codes:
#   0 — cache is fresh (skip Phase 1)
#   1 — cache is stale or missing (run Phase 1)
#
# Example:
#   bash scripts/check-cache.sh /path/to/source docs/
#   if [ $? -eq 0 ]; then echo "Cache hit — skip Phase 1"; fi

set -euo pipefail

SOURCE_DIR="${1:?Usage: check-cache.sh <source_dir> <docs_dir>}"
DOCS_DIR="${2:?Usage: check-cache.sh <source_dir> <docs_dir>}"

MANIFEST="$DOCS_DIR/_research/_manifest.json"
STALE_DAYS=30

# --- Check manifest exists ---
if [ ! -f "$MANIFEST" ]; then
  echo "MISS: no manifest at $MANIFEST"
  exit 1
fi

# --- Read cached values ---
cached_sha=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['source_sha'])" 2>/dev/null || echo "")
cached_count=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['source_file_count'])" 2>/dev/null || echo "")
cached_date=$(python3 -c "import json; print(json.load(open('$MANIFEST'))['cache_date'])" 2>/dev/null || echo "")

if [ -z "$cached_sha" ] || [ -z "$cached_count" ] || [ -z "$cached_date" ]; then
  echo "MISS: manifest is incomplete or malformed"
  exit 1
fi

# --- Compute current fingerprint ---
current_sha=$(git -C "$SOURCE_DIR" rev-parse --short HEAD 2>/dev/null || echo "no-git")
current_count=$(find "$SOURCE_DIR" -type f \( \
  -name '*.h' -o -name '*.cc' -o -name '*.cpp' -o \
  -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o \
  -name '*.java' -o -name '*.rs' -o -name '*.go' -o \
  -name '*.js' -o -name '*.jsx' \
\) 2>/dev/null | wc -l | tr -d ' ')

# --- Compare SHA ---
if [ "$current_sha" != "$cached_sha" ]; then
  echo "MISS: SHA changed ($cached_sha → $current_sha)"
  exit 1
fi

# --- Compare file count ---
if [ "$current_count" != "$cached_count" ]; then
  echo "MISS: file count changed ($cached_count → $current_count)"
  exit 1
fi

# --- Check staleness ---
if command -v python3 &>/dev/null; then
  is_stale=$(python3 -c "
from datetime import datetime, timedelta
cached = datetime.fromisoformat('$cached_date')
stale = (datetime.now() - cached).days > $STALE_DAYS
print('yes' if stale else 'no')
" 2>/dev/null || echo "no")
  if [ "$is_stale" = "yes" ]; then
    echo "MISS: cache is older than $STALE_DAYS days ($cached_date)"
    exit 1
  fi
fi

# --- All checks passed ---
echo "HIT: cache is fresh (sha=$cached_sha, files=$cached_count, date=$cached_date)"
exit 0

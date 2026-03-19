#!/usr/bin/env bash
# stale-check.sh — Report wiki pages whose wiki-generated date is older than N days.
#
# Usage:
#     bash stale-check.sh <wiki_dir> [max_age_days]
#
# Default max_age_days: 30
#
# Reads the <meta name="wiki-generated" content="YYYY-MM-DD"> tag from each
# HTML file and compares it to today's date.  Prints a summary of stale pages.

set -euo pipefail

WIKI_DIR="${1:?Usage: stale-check.sh <wiki_dir> [max_age_days]}"
MAX_AGE="${2:-30}"

if [[ ! -d "$WIKI_DIR" ]]; then
    echo "ERROR: $WIKI_DIR is not a directory" >&2
    exit 1
fi

TODAY_EPOCH=$(date +%s)
STALE=0
TOTAL=0
FRESH=0

echo "Checking wiki pages in $WIKI_DIR (max age: ${MAX_AGE} days)"
echo "────────────────────────────────────────────────────"

while IFS= read -r -d '' htmlfile; do
    TOTAL=$((TOTAL + 1))
    # Extract wiki-generated date from meta tag
    gen_date=$(grep -oP 'wiki-generated"\s+content="\K[0-9]{4}-[0-9]{2}-[0-9]{2}' "$htmlfile" 2>/dev/null || true)

    if [[ -z "$gen_date" ]]; then
        echo "  WARN   $(realpath --relative-to="$WIKI_DIR" "$htmlfile")  — no wiki-generated meta found"
        continue
    fi

    gen_epoch=$(date -d "$gen_date" +%s 2>/dev/null || echo "0")
    if [[ "$gen_epoch" == "0" ]]; then
        echo "  WARN   $(realpath --relative-to="$WIKI_DIR" "$htmlfile")  — unparseable date: $gen_date"
        continue
    fi

    age_days=$(( (TODAY_EPOCH - gen_epoch) / 86400 ))

    if [[ "$age_days" -gt "$MAX_AGE" ]]; then
        STALE=$((STALE + 1))
        echo "  STALE  $(realpath --relative-to="$WIKI_DIR" "$htmlfile")  — ${age_days}d old (generated $gen_date)"
    else
        FRESH=$((FRESH + 1))
    fi
done < <(find "$WIKI_DIR" -name '*.html' -print0 | sort -z)

echo "────────────────────────────────────────────────────"
echo "Total: $TOTAL | Fresh: $FRESH | Stale: $STALE (>${MAX_AGE}d)"

if [[ "$STALE" -gt 0 ]]; then
    exit 1
fi
exit 0

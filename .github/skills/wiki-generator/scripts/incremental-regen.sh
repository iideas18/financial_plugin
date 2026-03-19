#!/usr/bin/env bash
# incremental-regen.sh — Detect which wiki pages need regeneration based on git changes.
#
# Usage:
#   bash incremental-regen.sh <source_root> <docs_dir> [git_ref]
#
# Arguments:
#   source_root  — Root of the source code (e.g., .)
#   docs_dir     — Wiki output directory (e.g., docs/)
#   git_ref      — Git ref to diff against (default: HEAD~1). Use a branch/tag/SHA.
#
# Output:
#   Lists wiki pages that should be regenerated because their source directories changed.
#   Also lists new source directories that have no wiki page yet.
#
# Example:
#   bash incremental-regen.sh . docs/ HEAD~5
#   bash incremental-regen.sh . docs/ main

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <source_root> <docs_dir> [git_ref]" >&2
    exit 1
fi

SOURCE_ROOT="$1"
DOCS_DIR="$2"
GIT_REF="${3:-HEAD~1}"

if ! git -C "$SOURCE_ROOT" rev-parse --git-dir &>/dev/null; then
    echo "Error: $SOURCE_ROOT is not inside a git repository" >&2
    exit 1
fi

if [ ! -d "$DOCS_DIR" ]; then
    echo "Error: docs directory $DOCS_DIR does not exist" >&2
    exit 1
fi

echo "=== Incremental Wiki Regeneration Check ==="
echo "Source:   $SOURCE_ROOT"
echo "Docs:     $DOCS_DIR"
echo "Diff ref: $GIT_REF"
echo ""

# Get changed files relative to source root
CHANGED_FILES=$(git -C "$SOURCE_ROOT" diff --name-only "$GIT_REF" 2>/dev/null || true)

if [ -z "$CHANGED_FILES" ]; then
    echo "No changes detected since $GIT_REF"
    exit 0
fi

# Extract unique top-level and second-level directories that changed
CHANGED_DIRS=$(echo "$CHANGED_FILES" | \
    grep -E '\.(h|cc|cpp|c|py|ts|js|java|rs|go)$' | \
    awk -F/ '{
        if (NF >= 2) print $1;
        if (NF >= 3) print $1"/"$2;
    }' | sort -u)

if [ -z "$CHANGED_DIRS" ]; then
    echo "No source code directories changed since $GIT_REF"
    exit 0
fi

echo "Changed source directories:"
echo "$CHANGED_DIRS" | sed 's/^/  /'
echo ""

# Map changed directories to wiki pages
NEEDS_REGEN=()
NO_WIKI_PAGE=()

while IFS= read -r dir; do
    base=$(basename "$dir")
    parent=$(dirname "$dir")

    # Check various wiki page path patterns
    found=false
    for candidate in \
        "$DOCS_DIR/${base}_doc/index.html" \
        "$DOCS_DIR/${base}/index.html" \
        "$DOCS_DIR/$(basename "$parent")_doc/${base}/index.html"; do
        if [ -f "$candidate" ]; then
            NEEDS_REGEN+=("$candidate")
            found=true
        fi
    done

    if ! $found; then
        NO_WIKI_PAGE+=("$dir")
    fi
done <<< "$CHANGED_DIRS"

# Deduplicate
readarray -t NEEDS_REGEN < <(printf '%s\n' "${NEEDS_REGEN[@]}" | sort -u)

# Report results
if [ ${#NEEDS_REGEN[@]} -gt 0 ]; then
    echo "=== Pages needing regeneration (${#NEEDS_REGEN[@]}): ==="
    printf '  %s\n' "${NEEDS_REGEN[@]}"
else
    echo "=== No existing wiki pages need regeneration ==="
fi

echo ""

if [ ${#NO_WIKI_PAGE[@]} -gt 0 ]; then
    echo "=== Source dirs with no wiki page (${#NO_WIKI_PAGE[@]}): ==="
    printf '  %s\n' "${NO_WIKI_PAGE[@]}"
fi

echo ""

# Check for stale pages (wiki pages whose source dir no longer exists)
echo "=== Checking for stale pages ==="
STALE=0
find "$DOCS_DIR" -name 'index.html' -not -path '*/old/*' | while read -r page; do
    # Extract source path from meta tag if present
    src=$(grep -oP 'wiki-source"\s+content="\K[^"]+' "$page" 2>/dev/null || true)
    if [ -n "$src" ] && [ ! -d "$SOURCE_ROOT/$src" ]; then
        echo "  STALE: $page (source: $src)"
        STALE=$((STALE + 1))
    fi
done

if [ "$STALE" -eq 0 ]; then
    echo "  No stale pages found"
fi

echo ""
echo "Done. Regenerate listed pages by re-running the wiki generator for those modules."

#!/usr/bin/env bash
# publish-version.sh — Publish a versioned snapshot of the wiki.
#
# Creates a timestamped (or tagged) copy of the wiki output directory,
# maintaining a versions.json manifest for tracking history.
#
# Usage:
#     bash scripts/publish-version.sh <wiki_dir> [output_base] [--tag TAG]
#
# Examples:
#     bash scripts/publish-version.sh docs/                         # → docs_2026-03-17_143022/
#     bash scripts/publish-version.sh docs/ /tmp/wiki-archive       # → /tmp/wiki-archive/2026-03-17_143022/
#     bash scripts/publish-version.sh docs/ --tag v2.1              # → docs_v2.1/
#     bash scripts/publish-version.sh docs/ ~/archive --tag release3 # → ~/archive/release3/
#
# The script:
#   1. Copies the entire wiki directory to a versioned output directory
#   2. Stamps every HTML page with a <meta name="wiki-version"> tag
#   3. Updates versions.json in the output base with the new entry
#   4. Prints a summary of what was published

set -euo pipefail

WIKI_DIR="${1:?Usage: publish-version.sh <wiki_dir> [output_base] [--tag TAG]}"
shift

# Parse optional args
OUTPUT_BASE=""
TAG=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            TAG="${2:?--tag requires a value}"
            shift 2
            ;;
        *)
            OUTPUT_BASE="$1"
            shift
            ;;
    esac
done

# Validate source
if [[ ! -d "$WIKI_DIR" ]]; then
    echo "ERROR: $WIKI_DIR is not a directory" >&2
    exit 1
fi

# Generate version label
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
DATE_ISO=$(date +%Y-%m-%dT%H:%M:%S%z)
if [[ -n "$TAG" ]]; then
    VERSION_LABEL="$TAG"
else
    VERSION_LABEL="$TIMESTAMP"
fi

# Determine output directory
if [[ -n "$OUTPUT_BASE" ]]; then
    # Custom base: put version as subdirectory
    DEST_DIR="$OUTPUT_BASE/$VERSION_LABEL"
    MANIFEST_DIR="$OUTPUT_BASE"
else
    # Default: sibling directory next to wiki_dir
    WIKI_BASENAME=$(basename "$WIKI_DIR")
    WIKI_PARENT=$(dirname "$WIKI_DIR")
    DEST_DIR="$WIKI_PARENT/${WIKI_BASENAME}_${VERSION_LABEL}"
    MANIFEST_DIR="$WIKI_PARENT"
fi

# Safety: don't overwrite existing
if [[ -d "$DEST_DIR" ]]; then
    echo "ERROR: $DEST_DIR already exists. Choose a different tag or wait a second." >&2
    exit 1
fi

# Copy wiki
echo "Publishing wiki version: $VERSION_LABEL"
echo "  Source:      $WIKI_DIR"
echo "  Destination: $DEST_DIR"
cp -r "$WIKI_DIR" "$DEST_DIR"

# Count pages
PAGE_COUNT=$(find "$DEST_DIR" -name '*.html' | wc -l)

# Stamp every HTML page with version meta tag
find "$DEST_DIR" -name '*.html' -print0 | while IFS= read -r -d '' htmlfile; do
    # Insert wiki-version meta after wiki-generated (or after <head> if not found)
    if grep -q 'wiki-generated' "$htmlfile"; then
        sed -i '/wiki-generated/a <meta name="wiki-version" content="'"$VERSION_LABEL"'">' "$htmlfile"
    elif grep -q '<head>' "$htmlfile"; then
        sed -i '/<head>/a <meta name="wiki-version" content="'"$VERSION_LABEL"'">' "$htmlfile"
    fi
done

# Get git SHA if available
GIT_SHA=""
if command -v git &>/dev/null && git rev-parse --is-inside-work-tree &>/dev/null 2>&1; then
    GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "")
fi

# Update versions manifest
MANIFEST="$MANIFEST_DIR/versions.json"
NEW_ENTRY=$(cat <<EOF
{
    "version": "$VERSION_LABEL",
    "timestamp": "$DATE_ISO",
    "path": "$(realpath --relative-to="$MANIFEST_DIR" "$DEST_DIR" 2>/dev/null || echo "$DEST_DIR")",
    "pages": $PAGE_COUNT,
    "git_sha": "$GIT_SHA"
}
EOF
)

if [[ -f "$MANIFEST" ]]; then
    # Append to existing array — simple approach: insert before closing ]
    # Use Python for reliable JSON manipulation
    python3 -c "
import json, sys
with open('$MANIFEST', 'r') as f:
    data = json.load(f)
entry = json.loads('''$NEW_ENTRY''')
data['versions'].append(entry)
with open('$MANIFEST', 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || {
        echo "  WARN: Could not update $MANIFEST (will create new)"
        echo '{"versions": ['"$NEW_ENTRY"']}' | python3 -m json.tool > "$MANIFEST"
    }
else
    echo '{"versions": ['"$NEW_ENTRY"']}' | python3 -m json.tool > "$MANIFEST"
fi

echo
echo "Done!"
echo "  Version:  $VERSION_LABEL"
echo "  Pages:    $PAGE_COUNT"
echo "  Output:   $DEST_DIR"
echo "  Manifest: $MANIFEST"
[[ -n "$GIT_SHA" ]] && echo "  Git SHA:  $GIT_SHA"

#!/usr/bin/env bash
# verify.sh — Wiki verification script
# Usage: bash scripts/verify.sh docs/
#
# Checks all HTML wiki pages for required patterns, consistency, and broken links.
# Exit code: 0 = all pass, 1 = failures found

set -euo pipefail

DOCS_DIR="${1:?Usage: bash verify.sh <docs-dir>}"
PASS=0
FAIL=0
WARN=0

pass() { PASS=$((PASS+1)); }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
warn() { WARN=$((WARN+1)); echo "  WARN: $1"; }

echo "=== Wiki Verification ==="
echo "Scanning: $DOCS_DIR"
echo

# Collect all wiki HTML files (exclude any pre-existing non-wiki HTML like docs/html/)
mapfile -t FILES < <(find "$DOCS_DIR" -name '*.html' -not -path '*/html/*' -not -name '_*' | sort)
TOTAL=${#FILES[@]}
echo "Found $TOTAL HTML files"
echo

mermaid_count() {
  awk '/class="mermaid"/{count++} END{print count+0}' "$1"
}

# --- Check 1: Theme toggle ---
echo "[1/22] Theme toggle (themeToggle)"
for f in "${FILES[@]}"; do
  if ! grep -q 'themeToggle' "$f"; then
    fail "$f — missing theme toggle"
  else
    pass
  fi
done

# --- Check 2: startOnLoad:false ---
echo "[2/22] Mermaid startOnLoad:false"
for f in "${FILES[@]}"; do
  if grep -q 'startOnLoad:true' "$f"; then
    fail "$f — has startOnLoad:true"
  else
    pass
  fi
done

# --- Check 3: No innerHTML mermaid restore ---
echo "[3/22] No innerHTML mermaid restore"
for f in "${FILES[@]}"; do
  if grep -q 'el\.innerHTML=src\|el\.innerHTML = src' "$f"; then
    fail "$f — uses innerHTML for mermaid restore (use textContent)"
  else
    pass
  fi
done

# --- Check 4: pre code no color override ---
echo "[4/22] pre code CSS (no color override)"
for f in "${FILES[@]}"; do
  if grep -Pq 'pre\s+code\s*\{[^}]*color:\s*var\(--text\)' "$f"; then
    fail "$f — pre code sets color:var(--text), will break hljs"
  else
    pass
  fi
done

# --- Check 5: Intro boxes on L2 pages ---
echo "[5/22] Intro boxes on L2 pages"
for f in "$DOCS_DIR"/*_doc/*/index.html; do
  [ -f "$f" ] || continue
  if ! grep -q 'What is this' "$f"; then
    fail "$f — missing intro box"
  else
    pass
  fi
done

# --- Check 6: Glossary links ---
echo "[6/22] Glossary links in all pages"
for f in "${FILES[@]}"; do
  # Glossary page and search page don't need to link to glossary (search already has it)
  [[ "$f" == *glossary.html ]] && continue
  if ! grep -q 'glossary.html' "$f"; then
    fail "$f — missing glossary link"
  else
    pass
  fi
done

# --- Check 7: Minimum line counts ---
echo "[7/22] Minimum line counts (300+ lines)"
for f in "${FILES[@]}"; do
  # Search page and generated JSON companions are shorter by design
  [[ "$f" == *search.html || "$f" == *stats.html ]] && continue
  lines=$(wc -l < "$f")
  if [ "$lines" -lt 300 ]; then
    fail "$f — only $lines lines (minimum 300)"
  else
    pass
  fi
done

# --- Check 8: Mermaid diagram counts (2+ per page, except glossary) ---
echo "[8/23] Mermaid diagrams (2+ per page)"
for f in "${FILES[@]}"; do
  [[ "$f" == *glossary.html || "$f" == *search.html || "$f" == *stats.html ]] && continue
  count=$(mermaid_count "$f")
  if [ "$count" -lt 2 ]; then
    warn "$f — only $count mermaid diagram(s) (recommend 2+)"
  else
    pass
  fi
done

# --- Check 9: Broken internal links ---
echo "[9/23] Broken internal links"
for f in "${FILES[@]}"; do
  dir=$(dirname "$f")
  while IFS= read -r link; do
    [ -z "$link" ] && continue
    [[ "$link" == http* || "$link" == mailto* || "$link" == \#* || "$link" == javascript* ]] && continue
    # Strip any #fragment and ?query
    target="${link%%#*}"
    target="${target%%\?*}"
    [ -z "$target" ] && continue
    if [ ! -f "$dir/$target" ]; then
      fail "$f -> $link (resolved: $dir/$target)"
    else
      pass
    fi
  done < <(grep -oP 'href="\K[^"]+' "$f" 2>/dev/null)
done

# --- Check 10: Skip-link (accessibility) ---
echo "[10/23] Skip-link (accessibility)"
for f in "${FILES[@]}"; do
  if ! grep -q 'class="skip-link"' "$f"; then
    fail "$f — missing skip-link"
  else
    pass
  fi
done

# --- Check 11: aria-label on theme toggle ---
echo "[11/23] aria-label on theme toggle"
for f in "${FILES[@]}"; do
  if ! grep -q 'aria-label="Toggle light/dark theme"' "$f"; then
    fail "$f — theme toggle missing aria-label"
  else
    pass
  fi
done

# --- Check 12: Main content wrapper ---
echo "[12/23] Main content wrapper (<main id=\"main\">)"
for f in "${FILES[@]}"; do
  if ! grep -q '<main id="main">' "$f"; then
    fail "$f — missing <main id=\"main\"> wrapper"
  else
    pass
  fi
done

# --- Check 13: Print stylesheet ---
echo "[13/23] Print stylesheet (@media print)"
for f in "${FILES[@]}"; do
  if ! grep -q '@media print' "$f"; then
    fail "$f — missing print stylesheet"
  else
    pass
  fi
done

# --- Check 14: Freshness metadata ---
echo "[14/23] Freshness metadata (wiki-generated)"
for f in "${FILES[@]}"; do
  if ! grep -q 'wiki-generated' "$f"; then
    warn "$f — missing wiki-generated meta tag"
  else
    pass
  fi
done

# --- Check 15: Back-to-top button ---
echo "[15/23] Back-to-top button"
for f in "${FILES[@]}"; do
  if ! grep -q 'backToTop' "$f"; then
    fail "$f — missing back-to-top button"
  else
    pass
  fi
done

# --- Check 16: Code copy button on L1/L2 ---
echo "[16/23] Code copy button (L1/L2)"
for f in "${FILES[@]}"; do
  [[ "$f" == *glossary.html || "$f" == *search.html ]] && continue
  # Only check pages that have hljs (L1/L2)
  if grep -q 'highlightAll' "$f"; then
    if ! grep -q 'copy-btn' "$f"; then
      fail "$f — missing code copy button"
    else
      pass
    fi
  fi
done

# --- Check 17: Diagram overlay (L0/L1/L2) ---
echo "[17/23] Diagram overlay (L0/L1/L2)"
for f in "${FILES[@]}"; do
  [[ "$f" == *glossary.html || "$f" == *search.html ]] && continue
  if grep -q 'class="mermaid"' "$f"; then
    if ! grep -q 'diagramOverlay' "$f"; then
      fail "$f — missing diagram overlay"
    else
      pass
    fi
  fi
done

# --- Check 18: Source revision meta ---
echo "[18/23] Source revision meta (wiki-source-rev)"
for f in "${FILES[@]}"; do
  if ! grep -q 'wiki-source-rev' "$f"; then
    warn "$f — missing wiki-source-rev meta tag"
  else
    pass
  fi
done

# --- Check 19: Reading time (L1/L2) ---
echo "[19/23] Reading time estimate (L1/L2)"
for f in "${FILES[@]}"; do
  [[ "$f" == *glossary.html || "$f" == *search.html ]] && continue
  if grep -q 'highlightAll' "$f"; then
    if ! grep -q 'min read' "$f"; then
      warn "$f — missing reading time estimate"
    else
      pass
    fi
  fi
done

# --- Check 20: Print hides new UI elements ---
echo "[20/23] Print hides new UI elements"
for f in "${FILES[@]}"; do
  if grep -q '@media print' "$f"; then
    if ! grep -q 'back-to-top' "$f"; then
      warn "$f — print stylesheet may not hide back-to-top"
    else
      pass
    fi
  fi
done

# --- Check 21: Focus page parent meta ---
echo "[21/23] Focus page parent meta"
mapfile -t FOCUS_FILES < <(find "$DOCS_DIR" -name '*.html' -path '*/*/*/index.html' -not -path '*/html/*' 2>/dev/null | sort)
if [ ${#FOCUS_FILES[@]} -gt 0 ]; then
  for f in "${FOCUS_FILES[@]}"; do
    if grep -q 'wiki-focus-parent' "$f"; then
      # It's a focus page — check it has the parent meta
      parent_path=$(grep -oP 'wiki-focus-parent.*?content="\K[^"]+' "$f" || true)
      if [ -z "$parent_path" ]; then
        fail "$f — focus page missing parent path value"
      else
        pass
      fi
    fi
  done
else
  pass  # no focus pages yet
fi

# --- Check 22: Focus page back-link in parent ---
echo "[22/23] Focus page back-link in parent L2"
for f in "${FOCUS_FILES[@]}"; do
  if grep -q 'wiki-focus-parent' "$f"; then
    parent_rel=$(grep -oP 'wiki-focus-parent.*?content="\K[^"]+' "$f" || true)
    if [ -n "$parent_rel" ]; then
      parent_abs="$(dirname "$f")/$parent_rel"
      parent_abs=$(realpath "$parent_abs" 2>/dev/null || echo "")
      if [ -n "$parent_abs" ] && [ -f "$parent_abs" ]; then
        topic_slug=$(basename "$(dirname "$f")")
        if ! grep -q "$topic_slug" "$parent_abs"; then
          warn "$f — parent $parent_abs does not link back to focus page ($topic_slug)"
        else
          pass
        fi
      fi
    fi
  fi
done

# --- Check 23: Extraction consistency on parent L2 pages ---
echo "[23/23] Parent extraction consistency"
for f in "${FILES[@]}"; do
  [[ "$f" == *glossary.html || "$f" == *search.html || "$f" == *stats.html ]] && continue
  if grep -q 'id="deep-dives"' "$f" && grep -q 'class="card-grid"' "$f"; then
    focus_links=$(grep -oE 'href="[^"]+/index\.html"' "$f" | grep -cE '/[^/"]+/index\.html"$' || true)
    inline_deep_dives=$(grep -c 'class="deep-dive"' "$f" || true)
    if [ "$focus_links" -gt 0 ] && [ "$inline_deep_dives" -gt 0 ]; then
      warn "$f — mixed extracted focus hub and inline deep-dive sections; complete the extraction or remove the hub"
    else
      pass
    fi
  fi
done

# --- Summary ---
echo
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Warnings: $WARN"
echo "  Total files: $TOTAL"

if [ "$FAIL" -gt 0 ]; then
  echo
  echo "VERDICT: FAIL ($FAIL issues found)"
  exit 1
else
  echo
  echo "VERDICT: PASS (all checks passed)"
  exit 0
fi

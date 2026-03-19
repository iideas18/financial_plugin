#!/usr/bin/env bash
# diff-versions.sh — Compare two wiki version snapshots and produce a changelog.
#
# Usage:
#     bash scripts/diff-versions.sh <old_dir> <new_dir> [--html report.html]
#
# Examples:
#     bash scripts/diff-versions.sh docs_v1.0/ docs_v2.0/
#     bash scripts/diff-versions.sh docs_2026-03-01_120000/ docs/ --html changelog.html
#
# Output:
#   - New pages (in new but not old)
#   - Removed pages (in old but not new)
#   - Modified pages (content differs) with word-count delta
#   - Summary statistics
#   - Optional: HTML report with colored diffs

set -euo pipefail

OLD_DIR="${1:?Usage: diff-versions.sh <old_dir> <new_dir> [--html report.html]}"
NEW_DIR="${2:?Usage: diff-versions.sh <old_dir> <new_dir> [--html report.html]}"
shift 2

HTML_OUT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --html)
            HTML_OUT="${2:?--html requires an output file path}"
            shift 2
            ;;
        *) shift ;;
    esac
done

# Normalize trailing slashes
OLD_DIR="${OLD_DIR%/}"
NEW_DIR="${NEW_DIR%/}"

# Collect relative paths of HTML files in each directory
mapfile -t OLD_FILES < <(find "$OLD_DIR" -name '*.html' -not -path '*/html/*' -printf '%P\n' | sort)
mapfile -t NEW_FILES < <(find "$NEW_DIR" -name '*.html' -not -path '*/html/*' -printf '%P\n' | sort)

# Convert to associative arrays for fast lookup
declare -A OLD_SET NEW_SET
for f in "${OLD_FILES[@]}"; do OLD_SET["$f"]=1; done
for f in "${NEW_FILES[@]}"; do NEW_SET["$f"]=1; done

# Categorize
ADDED=()
REMOVED=()
MODIFIED=()
UNCHANGED=()

for f in "${NEW_FILES[@]}"; do
    if [[ -z "${OLD_SET[$f]:-}" ]]; then
        ADDED+=("$f")
    else
        if ! diff -q "$OLD_DIR/$f" "$NEW_DIR/$f" >/dev/null 2>&1; then
            MODIFIED+=("$f")
        else
            UNCHANGED+=("$f")
        fi
    fi
done

for f in "${OLD_FILES[@]}"; do
    if [[ -z "${NEW_SET[$f]:-}" ]]; then
        REMOVED+=("$f")
    fi
done

# Helper: word count from HTML (strip tags)
html_words() {
    sed 's/<[^>]*>//g' "$1" | wc -w | tr -d ' '
}

# Helper: line count
html_lines() {
    wc -l < "$1" | tr -d ' '
}

# --- Terminal Report ---
echo "=== Wiki Version Diff ==="
echo "Old: $OLD_DIR (${#OLD_FILES[@]} pages)"
echo "New: $NEW_DIR (${#NEW_FILES[@]} pages)"
echo

if [[ ${#ADDED[@]} -gt 0 ]]; then
    echo "── New Pages (${#ADDED[@]}) ──"
    for f in "${ADDED[@]}"; do
        words=$(html_words "$NEW_DIR/$f")
        echo "  + $f  ($words words)"
    done
    echo
fi

if [[ ${#REMOVED[@]} -gt 0 ]]; then
    echo "── Removed Pages (${#REMOVED[@]}) ──"
    for f in "${REMOVED[@]}"; do
        echo "  - $f"
    done
    echo
fi

if [[ ${#MODIFIED[@]} -gt 0 ]]; then
    echo "── Modified Pages (${#MODIFIED[@]}) ──"
    for f in "${MODIFIED[@]}"; do
        old_words=$(html_words "$OLD_DIR/$f")
        new_words=$(html_words "$NEW_DIR/$f")
        delta=$((new_words - old_words))
        sign=""
        [[ $delta -gt 0 ]] && sign="+"
        old_lines=$(html_lines "$OLD_DIR/$f")
        new_lines=$(html_lines "$NEW_DIR/$f")
        ldelta=$((new_lines - old_lines))
        lsign=""
        [[ $ldelta -gt 0 ]] && lsign="+"
        echo "  ~ $f  (${sign}${delta} words, ${lsign}${ldelta} lines)"
    done
    echo
fi

echo "── Summary ──"
echo "  Added:     ${#ADDED[@]}"
echo "  Removed:   ${#REMOVED[@]}"
echo "  Modified:  ${#MODIFIED[@]}"
echo "  Unchanged: ${#UNCHANGED[@]}"
echo "  Total old: ${#OLD_FILES[@]}  →  Total new: ${#NEW_FILES[@]}"

# --- Optional HTML Report ---
if [[ -n "$HTML_OUT" ]]; then
    cat > "$HTML_OUT" <<'HEADER'
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<title>Wiki Version Diff Report</title>
<style>
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--accent:#58a6ff;--green:#3fb950;--red:#f85149;--yellow:#d29922}
[data-theme="light"]{--bg:#fff;--surface:#f6f8fa;--border:#d0d7de;--text:#1f2328;--accent:#0969da;--green:#1a7f37;--red:#cf222e;--yellow:#9a6700}
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);max-width:900px;margin:0 auto;padding:2rem;line-height:1.6}
h1{color:var(--accent)}h2{border-bottom:1px solid var(--border);padding-bottom:.3rem}
table{width:100%;border-collapse:collapse;margin:1rem 0}th,td{padding:.5rem .8rem;border:1px solid var(--border);text-align:left}
th{background:var(--surface)}.added{color:var(--green)}.removed{color:var(--red)}.modified{color:var(--yellow)}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.8rem;font-weight:600}
.badge.add{background:var(--green);color:#fff}.badge.rem{background:var(--red);color:#fff}.badge.mod{background:var(--yellow);color:#fff}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin:1.5rem 0}
.summary .box{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem;text-align:center}
.summary .num{font-size:2rem;font-weight:700}.summary .label{font-size:.85rem;color:var(--text)}
.toggle{position:fixed;top:1rem;right:1rem;background:var(--surface);border:1px solid var(--border);border-radius:50%;width:36px;height:36px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.1rem;color:var(--text)}
</style>
</head>
<body>
<button class="toggle" onclick="var t=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',t);this.textContent=t==='light'?'☀':'☾'">☾</button>
HEADER

    cat >> "$HTML_OUT" <<EOF
<h1>Wiki Version Diff Report</h1>
<p><strong>Old:</strong> $OLD_DIR (${#OLD_FILES[@]} pages) &nbsp;→&nbsp; <strong>New:</strong> $NEW_DIR (${#NEW_FILES[@]} pages)</p>
<p>Generated: $(date -Iseconds)</p>

<div class="summary">
<div class="box"><div class="num added">${#ADDED[@]}</div><div class="label">Added</div></div>
<div class="box"><div class="num removed">${#REMOVED[@]}</div><div class="label">Removed</div></div>
<div class="box"><div class="num modified">${#MODIFIED[@]}</div><div class="label">Modified</div></div>
<div class="box"><div class="num">${#UNCHANGED[@]}</div><div class="label">Unchanged</div></div>
</div>
EOF

    if [[ ${#ADDED[@]} -gt 0 ]]; then
        echo '<h2>New Pages</h2><table><tr><th>Page</th><th>Words</th></tr>' >> "$HTML_OUT"
        for f in "${ADDED[@]}"; do
            words=$(html_words "$NEW_DIR/$f")
            echo "<tr><td class=\"added\">+ $f</td><td>$words</td></tr>" >> "$HTML_OUT"
        done
        echo '</table>' >> "$HTML_OUT"
    fi

    if [[ ${#REMOVED[@]} -gt 0 ]]; then
        echo '<h2>Removed Pages</h2><table><tr><th>Page</th></tr>' >> "$HTML_OUT"
        for f in "${REMOVED[@]}"; do
            echo "<tr><td class=\"removed\">- $f</td></tr>" >> "$HTML_OUT"
        done
        echo '</table>' >> "$HTML_OUT"
    fi

    if [[ ${#MODIFIED[@]} -gt 0 ]]; then
        echo '<h2>Modified Pages</h2><table><tr><th>Page</th><th>Word Δ</th><th>Line Δ</th></tr>' >> "$HTML_OUT"
        for f in "${MODIFIED[@]}"; do
            old_words=$(html_words "$OLD_DIR/$f")
            new_words=$(html_words "$NEW_DIR/$f")
            delta=$((new_words - old_words))
            sign=""
            [[ $delta -gt 0 ]] && sign="+"
            old_lines=$(html_lines "$OLD_DIR/$f")
            new_lines=$(html_lines "$NEW_DIR/$f")
            ldelta=$((new_lines - old_lines))
            lsign=""
            [[ $ldelta -gt 0 ]] && lsign="+"
            echo "<tr><td class=\"modified\">~ $f</td><td>${sign}${delta}</td><td>${lsign}${ldelta}</td></tr>" >> "$HTML_OUT"
        done
        echo '</table>' >> "$HTML_OUT"
    fi

    echo '</body></html>' >> "$HTML_OUT"
    echo
    echo "HTML report written to: $HTML_OUT"
fi

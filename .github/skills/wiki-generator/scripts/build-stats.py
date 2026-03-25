#!/usr/bin/env python3
"""build-stats.py — Generate a coverage dashboard (stats.html) for the wiki.

Scans docs/ and produces a self-contained HTML page showing:
  - Total pages, diagrams, focus pages
  - Per-module breakdown (pages, avg lines, diagrams, stale status)
  - Thin-page warnings, missing intro boxes, stale pages
  - Bar charts via inline SVG

Usage:
    python3 scripts/build-stats.py docs/
    python3 scripts/build-stats.py docs/ --out docs/stats.html
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

STALE_DAYS = 30


def scan_html(path: Path) -> dict:
    """Extract stats from a single HTML file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.count("\n") + 1
    diagrams = len(re.findall(r'class="mermaid"', text))
    has_intro = "What is this" in text
    has_toc = 'id="toc"' in text
    has_copy = "copy-btn" in text or "Copy" in text

    gen_match = re.search(r'wiki-generated.*?content="([^"]+)"', text)
    gen_date = gen_match.group(1) if gen_match else None

    source_match = re.search(r'wiki-source".*?content="([^"]+)"', text)
    source = source_match.group(1) if source_match else None

    is_focus = "wiki-focus-parent" in text

    # Word count (strip tags)
    stripped = re.sub(r"<[^>]+>", " ", text)
    stripped = re.sub(r"\s+", " ", stripped)
    words = len(stripped.split())

    return {
        "path": str(path),
        "lines": lines,
        "words": words,
        "diagrams": diagrams,
        "has_intro": has_intro,
        "has_toc": has_toc,
        "has_copy": has_copy,
        "gen_date": gen_date,
        "source": source,
        "is_focus": is_focus,
    }


def classify_page(rel_path: str) -> str:
    """Classify a page as L0, L1, L2, focus, search, or stats."""
    if "search" in rel_path:
        return "search"
    if "stats" in rel_path:
        return "stats"

    parts = Path(rel_path).parts
    # Focus: module_doc/submod/topic/index.html (4+ parts)
    if len(parts) >= 4 and parts[0].endswith("_doc"):
        return "focus"
    # L2: module_doc/submod/index.html (3 parts)
    if len(parts) >= 3 and parts[0].endswith("_doc"):
        return "L2"
    # L1: module_doc/index.html (2 parts) or module/index.html
    if len(parts) >= 2:
        return "L1"
    # L0: index.html at root
    return "L0"


def get_module(rel_path: str) -> str:
    """Extract module name from path."""
    parts = Path(rel_path).parts
    if len(parts) >= 1:
        return parts[0].replace("_doc", "")
    return "root"


def main():
    parser = argparse.ArgumentParser(description="Generate wiki coverage dashboard")
    parser.add_argument("docs_dir", help="Path to docs directory")
    parser.add_argument("--out", default=None, help="Output file (default: docs/stats.html)")
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS, help="Days before a page is stale")
    args = parser.parse_args()

    docs = Path(args.docs_dir)
    if not docs.is_dir():
        print(f"Error: {docs} is not a directory", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out) if args.out else docs / "stats.html"

    # Scan all HTML files
    html_files = sorted(docs.rglob("*.html"))
    html_files = [f for f in html_files if "/html/" not in str(f) and not f.name.startswith("_")]

    pages = []
    for f in html_files:
        rel = str(f.relative_to(docs))
        if rel == "stats.html":
            continue
        stats = scan_html(f)
        stats["rel_path"] = rel
        stats["level"] = classify_page(rel)
        stats["module"] = get_module(rel)
        pages.append(stats)

    # Aggregate stats
    total = len(pages)
    total_lines = sum(p["lines"] for p in pages)
    total_words = sum(p["words"] for p in pages)
    total_diagrams = sum(p["diagrams"] for p in pages)
    focus_count = sum(1 for p in pages if p["is_focus"])

    # Stale pages
    now = datetime.now()
    stale = []
    for p in pages:
        if p["gen_date"]:
            try:
                gen = datetime.fromisoformat(p["gen_date"].replace("Z", "+00:00").split("T")[0])
                age = (now - gen).days
                if age > args.stale_days:
                    stale.append((p["rel_path"], age))
            except (ValueError, TypeError):
                pass

    # Missing intro boxes (L2 + L1 pages)
    missing_intro = [p["rel_path"] for p in pages if p["level"] in ("L1", "L2") and not p["has_intro"]]

    # Thin pages
    thin = [(p["rel_path"], p["lines"]) for p in pages if p["lines"] < 218 and p["level"] not in ("search", "stats")]

    # Per-module stats
    modules = defaultdict(lambda: {"pages": 0, "lines": 0, "diagrams": 0, "focus": 0, "words": 0})
    for p in pages:
        if p["level"] in ("search", "stats"):
            continue
        m = modules[p["module"]]
        m["pages"] += 1
        m["lines"] += p["lines"]
        m["diagrams"] += p["diagrams"]
        m["words"] += p["words"]
        if p["is_focus"]:
            m["focus"] += 1

    # Level distribution
    level_counts = defaultdict(int)
    for p in pages:
        level_counts[p["level"]] += 1

    # Generate HTML
    max_lines = max((m["lines"] for m in modules.values()), default=1)

    module_rows = []
    for name in sorted(modules):
        m = modules[name]
        avg = m["lines"] // m["pages"] if m["pages"] > 0 else 0
        bar_pct = min(100, int(m["lines"] / max_lines * 100)) if max_lines > 0 else 0
        module_rows.append(
            f'<tr><td>{name}</td><td>{m["pages"]}</td><td>{avg}</td>'
            f'<td>{m["diagrams"]}</td><td>{m["focus"]}</td><td>{m["words"]:,}</td>'
            f'<td><div class="bar" style="width:{bar_pct}%"></div></td></tr>'
        )

    stale_rows = "\n".join(
        f"<tr><td>{p}</td><td>{age}d</td></tr>" for p, age in sorted(stale, key=lambda x: -x[1])
    )
    thin_rows = "\n".join(
        f"<tr><td>{p}</td><td>{lines}</td></tr>" for p, lines in sorted(thin, key=lambda x: x[1])
    )
    missing_rows = "\n".join(f"<tr><td>{p}</td></tr>" for p in missing_intro)

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wiki Coverage Dashboard</title>
<style>
:root{{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--text-muted:#8b949e;--accent:#58a6ff;--accent2:#3fb950;--accent3:#d29922;--accent4:#f85149;--heading:#f0f6fc;--code-bg:#1c2128}}
[data-theme="light"]{{--bg:#fff;--surface:#f6f8fa;--border:#d0d7de;--text:#1f2328;--text-muted:#656d76;--accent:#0969da;--accent2:#1a7f37;--accent3:#9a6700;--accent4:#cf222e;--heading:#1f2328;--code-bg:#f6f8fa}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);max-width:1100px;margin:0 auto;padding:2rem;line-height:1.6}}
h1{{color:var(--accent);margin-bottom:.5rem}}h2{{color:var(--heading);margin:2rem 0 1rem;border-bottom:1px solid var(--border);padding-bottom:.3rem}}
.subtitle{{color:var(--text-muted);margin-bottom:2rem}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem;margin:1.5rem 0}}
.kpi{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.2rem;text-align:center}}
.kpi .num{{font-size:2.2rem;font-weight:700;color:var(--accent)}}
.kpi .label{{font-size:.85rem;color:var(--text-muted)}}
.kpi.warn .num{{color:var(--accent4)}}
table{{width:100%;border-collapse:collapse;margin:.8rem 0}}th,td{{padding:.45rem .7rem;border:1px solid var(--border);text-align:left;font-size:.9rem}}
th{{background:var(--surface);font-weight:600}}tr:nth-child(even){{background:var(--surface)}}
.bar{{height:14px;background:var(--accent2);border-radius:3px;min-width:2px}}
.toggle{{position:fixed;top:1rem;right:1rem;background:var(--surface);border:1px solid var(--border);border-radius:50%;width:38px;height:38px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.1rem;color:var(--text);z-index:1000}}
.ok{{color:var(--accent2)}}.bad{{color:var(--accent4)}}
.empty{{color:var(--text-muted);font-style:italic;padding:1rem}}
@media print{{.toggle{{display:none}}body{{color:#1f2328;background:#fff}}}}
</style>
</head>
<body>
<button class="toggle" id="themeToggle" title="Toggle theme" aria-label="Toggle light/dark theme" onclick="var t=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',t);this.textContent=t==='light'?'☀':'☾'">☾</button>

<h1>📊 Wiki Coverage Dashboard</h1>
<p class="subtitle">Generated {now.strftime('%Y-%m-%d %H:%M')} &mdash; {docs}</p>

<div class="kpis">
<div class="kpi"><div class="num">{total}</div><div class="label">Total Pages</div></div>
<div class="kpi"><div class="num">{total_lines:,}</div><div class="label">Total Lines</div></div>
<div class="kpi"><div class="num">{total_words:,}</div><div class="label">Total Words</div></div>
<div class="kpi"><div class="num">{total_diagrams}</div><div class="label">Diagrams</div></div>
<div class="kpi"><div class="num">{focus_count}</div><div class="label">Focus Pages</div></div>
<div class="kpi {'warn' if len(stale) > 0 else ''}"><div class="num">{len(stale)}</div><div class="label">Stale Pages</div></div>
<div class="kpi {'warn' if len(thin) > 0 else ''}"><div class="num">{len(thin)}</div><div class="label">Thin Pages</div></div>
</div>

<h2>Level Distribution</h2>
<table>
<tr><th>Level</th><th>Count</th></tr>
{"".join(f'<tr><td>{lv}</td><td>{ct}</td></tr>' for lv, ct in sorted(level_counts.items()))}
</table>

<h2>Per-Module Breakdown</h2>
<table>
<tr><th>Module</th><th>Pages</th><th>Avg Lines</th><th>Diagrams</th><th>Focus</th><th>Words</th><th>Content (relative)</th></tr>
{"".join(module_rows)}
</table>

<h2>⚠️ Stale Pages (&gt;{args.stale_days} days)</h2>
{f'<table><tr><th>Page</th><th>Age</th></tr>{stale_rows}</table>' if stale else '<p class="empty">None — all pages are fresh.</p>'}

<h2>⚠️ Thin Pages (&lt;218 lines)</h2>
{f'<table><tr><th>Page</th><th>Lines</th></tr>{thin_rows}</table>' if thin else '<p class="empty">None — all pages meet minimum line count.</p>'}

<h2>⚠️ Missing Intro Boxes</h2>
{f'<table><tr><th>Page</th></tr>{missing_rows}</table>' if missing_intro else '<p class="empty">None — all L1/L2 pages have intro boxes.</p>'}

</body>
</html>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Dashboard written to: {out_path}")
    print(f"  {total} pages, {total_diagrams} diagrams")
    if stale:
        print(f"  ⚠ {len(stale)} stale page(s)")
    if thin:
        print(f"  ⚠ {len(thin)} thin page(s)")


if __name__ == "__main__":
    main()

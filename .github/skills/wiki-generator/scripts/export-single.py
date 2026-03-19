#!/usr/bin/env python3
"""export-single.py — Merge all wiki pages into a single self-contained HTML file.

Combines all wiki pages into one continuous HTML document suitable for
offline reading, email, or printing. Each page becomes a section with
a page break before it.

Usage:
    python3 scripts/export-single.py docs/
    python3 scripts/export-single.py docs/ --out wiki-export.html
    python3 scripts/export-single.py docs/ --toc          # with table of contents
"""

import argparse
import re
import sys
from pathlib import Path


def extract_title(html: str) -> str:
    """Extract <title> text from HTML."""
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    return m.group(1).strip() if m else "Untitled"


def extract_main(html: str) -> str:
    """Extract content inside <main>...</main>."""
    m = re.search(r"<main[^>]*>(.*?)</main>", html, re.DOTALL)
    return m.group(1) if m else ""


def extract_styles(html: str) -> str:
    """Extract all <style> blocks."""
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.DOTALL))


def classify_page(rel: str) -> tuple:
    """Return (sort_key, level_label) for ordering."""
    parts = Path(rel).parts
    if rel == "index.html":
        return (0, ""), "Hub"
    if "glossary" in rel:
        return (999, ""), "Glossary"
    if "search" in rel:
        return (998, ""), "Search"
    if "stats" in rel:
        return (997, ""), "Stats"
    # L1
    if len(parts) == 2:
        return (1, parts[0]), "Overview"
    # L2
    if len(parts) == 3:
        return (2, parts[0] + "/" + parts[1]), "Deep-Dive"
    # Focus
    if len(parts) >= 4:
        return (3, "/".join(parts[:-1])), "Focus"
    return (5, rel), ""


def main():
    parser = argparse.ArgumentParser(description="Export wiki to single HTML file")
    parser.add_argument("docs_dir", help="Path to docs directory")
    parser.add_argument("--out", default=None, help="Output file (default: <docs>-export.html)")
    parser.add_argument("--toc", action="store_true", help="Include table of contents")
    parser.add_argument("--skip-search", action="store_true", default=True, help="Skip search page")
    parser.add_argument("--skip-stats", action="store_true", default=True, help="Skip stats page")
    args = parser.parse_args()

    docs = Path(args.docs_dir)
    if not docs.is_dir():
        print(f"Error: {docs} is not a directory", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out) if args.out else Path(f"{docs.name}-export.html")

    # Collect pages
    html_files = sorted(docs.rglob("*.html"))
    html_files = [f for f in html_files if "/html/" not in str(f) and not f.name.startswith("_")]

    pages = []
    combined_css = set()

    for f in html_files:
        rel = str(f.relative_to(docs))
        if args.skip_search and "search" in rel:
            continue
        if args.skip_stats and "stats" in rel:
            continue

        text = f.read_text(encoding="utf-8", errors="replace")
        title = extract_title(text)
        main_content = extract_main(text)

        if not main_content:
            continue

        sort_key, level = classify_page(rel)
        slug = re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-")

        pages.append({
            "rel": rel,
            "title": title,
            "level": level,
            "content": main_content,
            "slug": slug,
            "sort_key": sort_key,
        })

        # Collect CSS from first page to use as base
        if not combined_css:
            css = extract_styles(text)
            if css:
                combined_css.add(css)

    # Sort pages: hub → L1 → L2 → focus → glossary
    pages.sort(key=lambda p: p["sort_key"])

    # Build TOC
    toc_html = ""
    if args.toc:
        toc_items = []
        for i, p in enumerate(pages):
            label = f'{p["level"]}: ' if p["level"] else ""
            toc_items.append(f'<li><a href="#{p["slug"]}">{label}{p["title"]}</a></li>')
        toc_html = f"""
<nav style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem;margin:2rem 0;">
<h2 style="margin-top:0;color:var(--accent);">Table of Contents</h2>
<ol style="columns:2;column-gap:2rem;">
{"".join(toc_items)}
</ol>
</nav>
"""

    # Build sections
    sections = []
    for p in pages:
        sections.append(f"""
<section id="{p['slug']}" style="page-break-before:always;margin-top:3rem;padding-top:2rem;border-top:2px solid var(--border);">
<div style="font-size:.8rem;color:var(--text-muted);margin-bottom:.5rem;">📄 {p['rel']}</div>
{p['content']}
</section>
""")

    base_css = "\n".join(combined_css) if combined_css else ""

    html = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wiki Export — {docs.name}</title>
<style>
{base_css}
body {{ max-width:1000px; margin:0 auto; padding:2rem; }}
section:first-of-type {{ page-break-before:auto; border-top:none; margin-top:1rem; }}
@media print {{
  .export-header {{ page-break-after:always; }}
  section {{ page-break-before:always; }}
  body {{ color:#1f2328; background:#fff; max-width:100%; padding:1rem; }}
  :root {{ --bg:#fff;--surface:#f6f8fa;--border:#d0d7de;--text:#1f2328;--text-muted:#656d76;--accent:#0969da;--accent2:#1a7f37;--accent3:#9a6700;--accent4:#cf222e;--heading:#1f2328;--code-bg:#f6f8fa }}
}}
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<link id="hljs-theme" rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
</head>
<body>
<div class="export-header">
<h1 style="color:var(--accent);font-size:2.5rem;">📚 {docs.name} Wiki</h1>
<p style="color:var(--text-muted);">{len(pages)} pages &mdash; exported {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
{toc_html}
</div>
{"".join(sections)}

<script>
document.querySelectorAll('pre.mermaid').forEach(function(el){{
  if(!el.getAttribute('data-source')) el.setAttribute('data-source',el.textContent);
}});
mermaid.initialize({{startOnLoad:false,theme:'dark',flowchart:{{useMaxWidth:true,htmlLabels:true,curve:'basis'}}}});
mermaid.run();
hljs.highlightAll();
</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    print(f"Exported {len(pages)} pages to: {out_path}")
    print(f"  File size: {out_path.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

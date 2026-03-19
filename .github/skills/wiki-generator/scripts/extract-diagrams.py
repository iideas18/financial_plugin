#!/usr/bin/env python3
"""extract-diagrams.py — Export Mermaid diagrams from wiki pages as standalone SVG files.

Extracts <pre class="mermaid"> blocks, renders them via mermaid-cli (mmdc),
and saves as individual SVG files named by page and diagram index.

Requirements:
    npm install -g @mermaid-js/mermaid-cli    (provides 'mmdc' command)

Usage:
    python3 scripts/extract-diagrams.py docs/
    python3 scripts/extract-diagrams.py docs/ --out diagrams/
    python3 scripts/extract-diagrams.py docs/ --theme dark
    python3 scripts/extract-diagrams.py docs/ --format png   # requires puppeteer
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check_mmdc():
    """Check if mermaid-cli is available."""
    if shutil.which("mmdc"):
        return True
    print("Error: 'mmdc' (mermaid-cli) not found.", file=sys.stderr)
    print("Install it with: npm install -g @mermaid-js/mermaid-cli", file=sys.stderr)
    return False


def extract_mermaid_blocks(html_path: Path) -> list:
    """Extract mermaid diagram source from an HTML file."""
    text = html_path.read_text(encoding="utf-8", errors="replace")
    blocks = []

    # Match <pre class="mermaid" data-source="...">
    for m in re.finditer(r'<pre\s+class="mermaid"[^>]*data-source="([^"]*)"', text):
        source = m.group(1)
        # Unescape HTML entities
        source = source.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
        if source.strip():
            blocks.append(source.strip())

    # Also match <pre class="mermaid">...content...</pre> without data-source
    for m in re.finditer(r'<pre\s+class="mermaid"[^>]*>(.*?)</pre>', text, re.DOTALL):
        content = m.group(1).strip()
        # Skip if it looks like it was already rendered (contains SVG)
        if "<svg" in content:
            continue
        # Unescape
        content = content.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
        if content and content not in blocks:
            blocks.append(content)

    return blocks


def render_diagram(source: str, output_path: Path, theme: str, fmt: str) -> bool:
    """Render a mermaid diagram to SVG/PNG using mmdc."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False) as tmp:
        tmp.write(source)
        tmp_path = tmp.name

    try:
        cmd = [
            "mmdc",
            "-i", tmp_path,
            "-o", str(output_path),
            "-t", theme,
            "-b", "transparent",
        ]
        if fmt == "png":
            cmd.extend(["-s", "2"])  # 2x scale for crisp PNGs

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  Warning: mmdc failed for {output_path.name}: {result.stderr.strip()}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"  Warning: mmdc timed out for {output_path.name}", file=sys.stderr)
        return False
    finally:
        os.unlink(tmp_path)


def main():
    parser = argparse.ArgumentParser(description="Extract Mermaid diagrams as SVG/PNG")
    parser.add_argument("docs_dir", help="Path to docs directory")
    parser.add_argument("--out", default=None, help="Output directory (default: docs/diagrams/)")
    parser.add_argument("--theme", choices=["dark", "default", "forest", "neutral"], default="default",
                        help="Mermaid theme (default: default)")
    parser.add_argument("--format", choices=["svg", "png"], default="svg", help="Output format")
    parser.add_argument("--dry-run", action="store_true", help="List diagrams without rendering")
    args = parser.parse_args()

    docs = Path(args.docs_dir)
    if not docs.is_dir():
        print(f"Error: {docs} is not a directory", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out) if args.out else docs / "diagrams"

    if not args.dry_run and not check_mmdc():
        sys.exit(1)

    # Scan all HTML files
    html_files = sorted(docs.rglob("*.html"))
    html_files = [f for f in html_files if "/html/" not in str(f) and not f.name.startswith("_")]

    total_diagrams = 0
    rendered = 0
    failed = 0

    for html_path in html_files:
        rel = str(html_path.relative_to(docs))
        blocks = extract_mermaid_blocks(html_path)

        if not blocks:
            continue

        # Create output subdirectory mirroring the page structure
        page_slug = re.sub(r"[/\\]", "_", rel.replace("/index.html", "").replace(".html", ""))
        if not page_slug:
            page_slug = "hub"

        for i, source in enumerate(blocks):
            total_diagrams += 1

            # Detect diagram type for naming
            dtype = "diagram"
            if source.strip().startswith("flowchart") or source.strip().startswith("graph"):
                dtype = "flowchart"
            elif source.strip().startswith("sequenceDiagram"):
                dtype = "sequence"
            elif source.strip().startswith("classDiagram"):
                dtype = "class"
            elif source.strip().startswith("stateDiagram"):
                dtype = "state"
            elif source.strip().startswith("erDiagram"):
                dtype = "er"
            elif source.strip().startswith("pie"):
                dtype = "pie"

            filename = f"{page_slug}_{i+1}_{dtype}.{args.format}"
            out_path = out_dir / filename

            if args.dry_run:
                first_line = source.split("\n")[0][:60]
                print(f"  {filename}  ←  {rel}  ({first_line}...)")
                continue

            out_dir.mkdir(parents=True, exist_ok=True)
            if render_diagram(source, out_path, args.theme, args.format):
                rendered += 1
                print(f"  ✓ {filename}")
            else:
                failed += 1

    print()
    if args.dry_run:
        print(f"Found {total_diagrams} diagram(s) across {len(html_files)} pages (dry run)")
    else:
        print(f"Extracted {rendered}/{total_diagrams} diagrams to: {out_dir}")
        if failed:
            print(f"  ⚠ {failed} diagram(s) failed to render")


if __name__ == "__main__":
    main()

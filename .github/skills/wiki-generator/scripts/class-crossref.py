#!/usr/bin/env python3
"""class-crossref.py — Add cross-reference links for class/struct names across wiki pages.

Scans all wiki pages to build a class→page mapping, then hyperlinks the first
occurrence of each class name in other pages' body text to the defining page.

This goes beyond auto-crosslink.py (which links module/sub-module names) by
linking individual class and struct names found in "Key Classes" tables.

Usage:
    python3 scripts/class-crossref.py docs/
    python3 scripts/class-crossref.py docs/ --dry-run
"""

import argparse
import os
import re
import sys
from pathlib import Path


SKIP_TAGS = {"a", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "script", "style"}

# Minimum class name length to avoid false positives on short names
MIN_NAME_LEN = 4


def extract_class_names(html: str) -> list:
    """Extract class/struct names from 'Key Classes' or similar tables.

    Looks for table rows where the first cell contains a class-like identifier
    (CamelCase or snake_case with uppercase).
    """
    names = set()

    # Find tables that likely contain class definitions
    # Look for <td> cells with code-like names (CamelCase, UPPER_CASE, etc.)
    table_pattern = re.compile(
        r"<table[^>]*>(.*?)</table>", re.DOTALL | re.IGNORECASE
    )

    for table_match in table_pattern.finditer(html):
        table_html = table_match.group(1)

        # Check if this table header mentions class/struct/component
        header_text = re.sub(r"<[^>]+>", " ", table_html[:500]).lower()
        if not any(kw in header_text for kw in ("class", "struct", "component", "file", "module")):
            continue

        # Extract first column of each row
        for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL):
            row = row_match.group(1)
            # Skip header rows
            if "<th" in row:
                continue

            # Get first <td>
            td_match = re.search(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if not td_match:
                continue

            cell = td_match.group(1)
            # Strip tags, get text
            text = re.sub(r"<[^>]+>", "", cell).strip()

            # Check if it looks like a class/struct name
            # CamelCase: starts with uppercase, contains lowercase
            # Or underscore_separated with some uppercase
            if (
                len(text) >= MIN_NAME_LEN
                and re.match(r"^[A-Z][A-Za-z0-9_]+$", text)
                and not text.isupper()  # skip ALL_CAPS constants
            ):
                names.add(text)

    return sorted(names)


def build_class_index(docs: Path) -> dict:
    """Build a mapping: class_name → (defining_page_rel_path, page_title)."""
    index = {}

    html_files = sorted(docs.rglob("*.html"))
    html_files = [
        f for f in html_files
        if "/html/" not in str(f)
        and not f.name.startswith("_")
        and "search" not in f.name
        and "stats" not in f.name
    ]

    for html_path in html_files:
        rel = str(html_path.relative_to(docs))
        text = html_path.read_text(encoding="utf-8", errors="replace")

        # Get page title
        title_match = re.search(r"<title>(.*?)</title>", text)
        title = title_match.group(1).strip() if title_match else rel

        classes = extract_class_names(text)
        for cls in classes:
            if cls not in index:
                index[cls] = (rel, title)

    return index


def linkify_classes(html: str, page_rel: str, class_index: dict) -> tuple:
    """Replace first occurrence of each class name with a link to its defining page.

    Returns (modified_html, count_of_links_added).
    """
    # Only process <main> content
    main_match = re.search(r"(<main[^>]*>)(.*?)(</main>)", html, re.DOTALL)
    if not main_match:
        return html, 0

    prefix = html[:main_match.start(2)]
    body = main_match.group(2)
    suffix = html[main_match.end(2):]

    count = 0

    for cls_name, (target_rel, target_title) in sorted(class_index.items(), key=lambda x: -len(x[0])):
        # Don't link to self
        if target_rel == page_rel:
            continue

        # Compute relative path from current page to target
        from_dir = Path(page_rel).parent
        to_path = Path(target_rel)
        try:
            rel_link = os.path.relpath(to_path, from_dir)
        except ValueError:
            continue

        # Find first occurrence not inside skip tags
        # Use a simple approach: find the class name as a whole word
        pattern = re.compile(r"(?<![<\w/])(" + re.escape(cls_name) + r")(?!\w)", re.DOTALL)

        def is_inside_skip_tag(pos: int, text: str) -> bool:
            """Check if position is inside a tag we should skip."""
            # Find the most recent opening tag before this position
            before = text[:pos]
            # Find last < that isn't closed
            tag_stack = []
            for m in re.finditer(r"<(/?)(\w+)[^>]*>", before):
                tag = m.group(2).lower()
                if m.group(1):  # closing tag
                    if tag_stack and tag_stack[-1] == tag:
                        tag_stack.pop()
                else:
                    if tag in SKIP_TAGS:
                        tag_stack.append(tag)
            return len(tag_stack) > 0

        match = pattern.search(body)
        while match:
            if not is_inside_skip_tag(match.start(), body):
                link = f'<a href="{rel_link}" title="{target_title}" class="xref">{cls_name}</a>'
                body = body[:match.start()] + link + body[match.end():]
                count += 1
                break  # Only link first occurrence
            # Try next occurrence
            match = pattern.search(body, match.end())

    return prefix + body + suffix, count


def main():
    parser = argparse.ArgumentParser(description="Cross-reference class names across wiki pages")
    parser.add_argument("docs_dir", help="Path to docs directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be linked without modifying files")
    parser.add_argument("--no-backup", action="store_true", help="Skip creating .bak files")
    args = parser.parse_args()

    docs = Path(args.docs_dir)
    if not docs.is_dir():
        print(f"Error: {docs} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Need os for relpath
    import os

    print("Building class index...")
    class_index = build_class_index(docs)
    print(f"  Found {len(class_index)} class/struct names across wiki pages")

    if not class_index:
        print("No classes found to cross-reference.")
        return

    if args.dry_run:
        print("\nClass index:")
        for cls, (rel, title) in sorted(class_index.items()):
            print(f"  {cls} → {rel}")
        print()

    # Process each page
    html_files = sorted(docs.rglob("*.html"))
    html_files = [
        f for f in html_files
        if "/html/" not in str(f)
        and not f.name.startswith("_")
        and "search" not in f.name
        and "stats" not in f.name
    ]

    total_links = 0
    modified_files = 0

    for html_path in html_files:
        rel = str(html_path.relative_to(docs))
        text = html_path.read_text(encoding="utf-8", errors="replace")

        modified, count = linkify_classes(text, rel, class_index)

        if count > 0:
            if args.dry_run:
                print(f"  Would add {count} cross-ref(s) in {rel}")
            else:
                if not args.no_backup:
                    bak = html_path.with_suffix(".html.bak")
                    if not bak.exists():
                        html_path.rename(bak)
                        bak.with_name(html_path.name)
                        # Re-read since rename moved the file
                        Path(str(bak)).rename(html_path.with_suffix(".html.bak2"))
                        # Actually, just write backup copy
                        html_path.with_suffix(".html.bak").write_text(text, encoding="utf-8")

                html_path.write_text(modified, encoding="utf-8")
                print(f"  ✓ {rel}: +{count} cross-ref(s)")

            total_links += count
            modified_files += 1

    print(f"\n{'Would add' if args.dry_run else 'Added'} {total_links} cross-references in {modified_files} files")


if __name__ == "__main__":
    main()

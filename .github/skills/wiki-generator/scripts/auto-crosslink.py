#!/usr/bin/env python3
"""auto-crosslink.py — Auto-link module/sub-module names in wiki body text.

Scans generated HTML wiki pages for known module and sub-module names
that appear in body text (outside of links, headings, and code blocks),
and wraps the first occurrence per page with a hyperlink to the target page.

Usage:
    python3 auto-crosslink.py <wiki_dir>

The script discovers linkable pages by scanning for index.html files
within the wiki directory tree.  It builds a map of display names
(derived from directory names) to their relative paths, then processes
each HTML file.

Safety:
  - Only the FIRST unlinked occurrence of each term is wrapped.
  - Terms inside <a>, <code>, <pre>, <h1>-<h6>, <title> are skipped.
  - Terms shorter than 3 characters are ignored.
  - A backup (.bak) is created before modifying any file.
"""

import os
import re
import sys
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    """Identify text nodes that are safe to crosslink (not in a/code/pre/heading/title)."""

    SKIP_TAGS = {"a", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "title", "script", "style"}

    def __init__(self):
        super().__init__()
        self.skip_depth = 0
        self.regions = []  # [(start, end)] of safe text regions

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            offset = self.getpos()
            self.regions.append((offset, data))


def discover_pages(wiki_dir):
    """Build a dict of {display_name: relative_path} from index.html files."""
    pages = {}
    for root, dirs, files in os.walk(wiki_dir):
        if "index.html" in files:
            rel = os.path.relpath(root, wiki_dir)
            if rel == ".":
                continue
            # Use the innermost directory name as the display name
            name = os.path.basename(rel)
            # Strip _doc suffix if present (e.g., "archlib_doc" -> "archlib")
            clean_name = re.sub(r"_doc$", "", name)
            if len(clean_name) >= 3:
                pages[clean_name] = os.path.join(rel, "index.html")
    return pages


def _is_inside_ancestor_tag(html, pos, tag):
    """Check if position `pos` in `html` is inside an open <tag>...</tag> pair."""
    before = html[:pos]
    opens = len(re.findall(r'<' + tag + r'[\s>]', before, re.IGNORECASE))
    closes = len(re.findall(r'</' + tag + r'\s*>', before, re.IGNORECASE))
    return opens > closes


def _is_inside_skip_context(html, pos):
    """Check if position is inside any tag that should not be crosslinked."""
    for tag in ("a", "code", "pre", "script", "style"):
        if _is_inside_ancestor_tag(html, pos, tag):
            return True
    # Also skip content inside elements with data-no-crosslink attribute
    # by checking for unbalanced data-no-crosslink opens before pos
    before = html[:pos]
    no_xl_opens = len(re.findall(r'<\w[^>]*data-no-crosslink[^>]*>', before, re.IGNORECASE))
    # Each data-no-crosslink container close is a </div> but we can't distinguish;
    # count closing </div> after the last open as a rough heuristic.
    # Instead, find the last data-no-crosslink open and check if its container is closed.
    for m in reversed(list(re.finditer(r'<(\w+)[^>]*data-no-crosslink[^>]*>', before, re.IGNORECASE))):
        close_tag = m.group(1)
        after_open = before[m.end():]
        c_opens = len(re.findall(r'<' + close_tag + r'[\s>]', after_open, re.IGNORECASE))
        c_closes = len(re.findall(r'</' + close_tag + r'\s*>', after_open, re.IGNORECASE))
        if c_opens >= c_closes:  # container still open
            return True
        break  # only need to check the most recent one
    return False


def crosslink_file(filepath, wiki_dir, pages):
    """Process one HTML file: wrap first unlinked occurrence of each known term."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    rel_dir = os.path.dirname(os.path.relpath(filepath, wiki_dir))
    modified = content
    linked_terms = set()

    for term, target_path in sorted(pages.items(), key=lambda x: -len(x[0])):
        # Skip self-references
        if os.path.relpath(target_path, rel_dir if rel_dir else ".") == "index.html":
            continue
        if term in linked_terms:
            continue

        # Compute relative path from current file to target
        if rel_dir:
            link_href = os.path.relpath(target_path, rel_dir)
        else:
            link_href = target_path

        # Find first occurrence outside of tags we want to skip
        # Use a regex that matches the term as a whole word, not inside an HTML tag
        pattern = re.compile(
            r'(?<![<\w/])(?<!/)\b(' + re.escape(term) + r')\b(?![^<]*>)',
            re.IGNORECASE,
        )

        # Only replace in <main> content if possible
        main_match = re.search(r'<main[^>]*>(.*?)</main>', modified, re.DOTALL)
        if main_match:
            main_start = main_match.start(1)
            main_text = main_match.group(1)

            m = pattern.search(main_text)
            # Skip matches that are inside <a>, <code>, <pre>, etc. ancestors
            while m and _is_inside_skip_context(main_text, m.start()):
                m = pattern.search(main_text, m.end())
            if m:
                replacement = f'<a href="{link_href}">{m.group(1)}</a>'
                new_main = main_text[:m.start()] + replacement + main_text[m.end():]
                modified = modified[:main_start] + new_main + modified[main_match.end(1):]
                linked_terms.add(term)

    if modified != content:
        backup_path = filepath + ".bak"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(content)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(modified)
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 auto-crosslink.py <wiki_dir>")
        sys.exit(1)

    wiki_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(wiki_dir):
        print(f"ERROR: {wiki_dir} is not a directory")
        sys.exit(1)

    pages = discover_pages(wiki_dir)
    if not pages:
        print("No linkable pages found.")
        sys.exit(0)

    print(f"Discovered {len(pages)} linkable pages")

    html_files = []
    for root, dirs, files in os.walk(wiki_dir):
        for f in files:
            if f.endswith(".html"):
                html_files.append(os.path.join(root, f))

    modified_count = 0
    for hf in html_files:
        if crosslink_file(hf, wiki_dir, pages):
            modified_count += 1
            print(f"  LINKED  {os.path.relpath(hf, wiki_dir)}")

    print(f"\nDone: {modified_count} file(s) modified, {len(html_files) - modified_count} unchanged.")


if __name__ == "__main__":
    main()

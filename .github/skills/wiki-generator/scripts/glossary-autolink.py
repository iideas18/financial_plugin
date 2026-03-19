#!/usr/bin/env python3
"""
glossary-autolink.py — Auto-link glossary terms in wiki pages.

Scans docs/glossary.html for <dt> terms, then searches all other wiki pages
for first occurrences of those terms and wraps them in <a> links pointing to
the glossary with the appropriate relative path.

Usage:
    python3 scripts/glossary-autolink.py docs/

Only links the FIRST occurrence of each term per page. Skips terms already
inside <a>, <code>, <pre>, <h1>-<h4>, or <dt>/<dd> tags.
"""

import os
import re
import sys
from html.parser import HTMLParser


def extract_glossary_terms(glossary_path):
    """Extract term names from <dt> tags in the glossary file."""
    terms = []
    with open(glossary_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Match <dt><code>TERM</code> or <dt>TERM patterns
    for m in re.finditer(r'<dt>(?:<code>)?([^<]+?)(?:</code>)?(?:\s*—[^<]*)?</dt>', content):
        term = m.group(1).strip()
        if len(term) >= 2:  # skip single-char terms
            terms.append(term)
    return sorted(set(terms), key=len, reverse=True)  # longest first to avoid partial matches


def get_glossary_relpath(page_path, docs_dir):
    """Compute relative path from page to glossary.html."""
    page_dir = os.path.dirname(os.path.abspath(page_path))
    glossary_abs = os.path.join(os.path.abspath(docs_dir), 'glossary.html')
    return os.path.relpath(glossary_abs, page_dir)


class TagTracker(HTMLParser):
    """Track which character positions are inside tags that should not be linked."""

    def __init__(self, html):
        super().__init__()
        self.skip_ranges = []   # (start, end) ranges to skip
        self._skip_tags = {'a', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'dt', 'dd', 'script', 'style', 'title'}
        self._stack = []
        self._html = html
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            pos = self.getpos()
            # getpos returns (line, col) — convert to char offset
            offset = self._line_col_to_offset(pos[0], pos[1])
            self._stack.append((tag.lower(), offset))

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags and self._stack:
            start_tag, start_offset = self._stack.pop()
            if start_tag == tag.lower():
                pos = self.getpos()
                end_offset = self._line_col_to_offset(pos[0], pos[1])
                # extend past closing tag
                close_tag = f'</{tag}>'
                idx = self._html.find(close_tag, end_offset - len(close_tag) - 5)
                if idx >= 0:
                    end_offset = idx + len(close_tag)
                self.skip_ranges.append((start_offset, end_offset))

    def _line_col_to_offset(self, line, col):
        offset = 0
        for i, l in enumerate(self._html.split('\n'), 1):
            if i == line:
                return offset + col
            offset += len(l) + 1  # +1 for newline
        return offset

    def is_skipped(self, start, end):
        for s, e in self.skip_ranges:
            if start >= s and end <= e:
                return True
        return False


def autolink_page(page_path, terms, docs_dir):
    """Add glossary links to first occurrence of each term in a page."""
    with open(page_path, 'r', encoding='utf-8') as f:
        content = f.read()

    glossary_rel = get_glossary_relpath(page_path, docs_dir)
    tracker = TagTracker(content)
    linked_terms = set()
    changes = 0

    for term in terms:
        if term in linked_terms:
            continue
        # Case-insensitive word-boundary match
        pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
        match = pattern.search(content)
        while match:
            start, end = match.start(), match.end()
            if not tracker.is_skipped(start, end):
                # Check we're not inside an HTML tag attribute
                before = content[max(0, start - 200):start]
                if '<' in before and '>' not in before[before.rfind('<'):]:
                    match = pattern.search(content, end)
                    continue
                original = match.group(0)
                replacement = f'<a href="{glossary_rel}#:~:text={term}" title="Glossary: {term}" style="border-bottom:1px dotted var(--accent);text-decoration:none">{original}</a>'
                content = content[:start] + replacement + content[end:]
                linked_terms.add(term)
                changes += 1
                break
            match = pattern.search(content, end)

    if changes > 0:
        with open(page_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return changes


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 glossary-autolink.py <docs-dir>")
        sys.exit(1)

    docs_dir = sys.argv[1]
    glossary_path = os.path.join(docs_dir, 'glossary.html')

    if not os.path.isfile(glossary_path):
        print(f"Error: glossary.html not found in {docs_dir}")
        sys.exit(1)

    terms = extract_glossary_terms(glossary_path)
    print(f"Found {len(terms)} glossary terms")

    total_changes = 0
    for root, _, files in os.walk(docs_dir):
        for fname in sorted(files):
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)
            # Skip glossary itself and non-wiki files
            if fpath == os.path.abspath(glossary_path):
                continue
            if '/html/' in fpath:
                continue
            changes = autolink_page(fpath, terms, docs_dir)
            rel = os.path.relpath(fpath, docs_dir)
            if changes:
                print(f"  {rel}: linked {changes} terms")
            else:
                print(f"  {rel}: (no changes)")
            total_changes += changes

    print(f"\nDone. Linked {total_changes} terms across wiki pages.")


if __name__ == '__main__':
    main()

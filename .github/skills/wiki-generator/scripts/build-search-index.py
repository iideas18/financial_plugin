#!/usr/bin/env python3
"""Build search-index.json from all HTML wiki pages in a docs directory.

Usage:
    python3 build-search-index.py docs/

Outputs: docs/search-index.json

The JSON format is an array of objects:
[
  {
    "title": "Page Title",
    "path": "relative/path/index.html",
    "excerpt": "first ~500 chars of visible text",
    "headings": ["H2 heading", "H3 heading", ...]
  }
]
"""

import json
import os
import re
import sys
from html.parser import HTMLParser


class WikiPageParser(HTMLParser):
    """Extract title, headings, and visible text from a wiki HTML page."""

    def __init__(self):
        super().__init__()
        self._tag_stack = []
        self._skip_tags = {'script', 'style', 'noscript'}
        self._in_skip = 0
        self.title = ''
        self.headings = []
        self.text_parts = []
        self._in_title = False
        self._in_heading = False
        self._heading_text = ''

    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)
        if tag in self._skip_tags:
            self._in_skip += 1
        if tag == 'title':
            self._in_title = True
        if tag in ('h2', 'h3'):
            self._in_heading = True
            self._heading_text = ''

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._in_skip = max(0, self._in_skip - 1)
        if tag == 'title':
            self._in_title = False
        if tag in ('h2', 'h3') and self._in_heading:
            self._in_heading = False
            cleaned = self._heading_text.strip()
            if cleaned:
                self.headings.append(cleaned)
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_heading:
            self._heading_text += data
        if self._in_skip == 0:
            self.text_parts.append(data)

    def get_excerpt(self, max_len=500):
        text = ' '.join(self.text_parts)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > max_len:
            text = text[:max_len].rsplit(' ', 1)[0] + '…'
        return text


def build_index(docs_dir):
    """Walk docs_dir and build search index entries."""
    index = []
    docs_dir = os.path.normpath(docs_dir)

    for root, _dirs, files in os.walk(docs_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            # Skip search page itself
            if fname == 'search.html':
                continue

            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, docs_dir)

            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except OSError:
                continue

            parser = WikiPageParser()
            parser.feed(content)

            title = parser.title.strip() or rel_path
            excerpt = parser.get_excerpt()
            headings = parser.headings

            if not excerpt:
                continue

            index.append({
                'title': title,
                'path': rel_path,
                'excerpt': excerpt,
                'headings': headings,
            })

    # Sort by path for deterministic output
    index.sort(key=lambda e: e['path'])
    return index


def main():
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <docs_dir>', file=sys.stderr)
        sys.exit(1)

    docs_dir = sys.argv[1]
    if not os.path.isdir(docs_dir):
        print(f'Error: {docs_dir} is not a directory', file=sys.stderr)
        sys.exit(1)

    index = build_index(docs_dir)
    out_path = os.path.join(docs_dir, 'search-index.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print(f'Built search index: {len(index)} pages -> {out_path}')


if __name__ == '__main__':
    main()

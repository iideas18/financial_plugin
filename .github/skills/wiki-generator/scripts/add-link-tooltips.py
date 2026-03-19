#!/usr/bin/env python3
"""Add title-attribute tooltips to internal wiki links for preview on hover.

Usage:
    python3 add-link-tooltips.py docs/

For each internal link (href not starting with http/mailto/#), this script:
1. Finds the target page
2. Extracts its .hero .subtitle or <title> text
3. Injects a title="..." attribute on the <a> tag for hover preview

Only modifies links that don't already have a title attribute.
"""

import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote


class PageMetaExtractor(HTMLParser):
    """Extract subtitle and title from a wiki page."""
    def __init__(self):
        super().__init__()
        self._in_title = False
        self._in_subtitle = False
        self.title = ''
        self.subtitle = ''
        self._tag_stack = []

    def handle_starttag(self, tag, attrs):
        self._tag_stack.append(tag)
        attr_dict = dict(attrs)
        if tag == 'title':
            self._in_title = True
        # Match <p class="subtitle"> or <div class="subtitle">
        cls = attr_dict.get('class', '')
        if 'subtitle' in cls and tag in ('p', 'div'):
            self._in_subtitle = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        if self._in_subtitle and tag in ('p', 'div'):
            self._in_subtitle = False
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_subtitle:
            self.subtitle += data


def get_page_tooltip(filepath):
    """Get tooltip text for a page (subtitle preferred, fallback to title)."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(8192)  # Subtitle/title are near the top
    except OSError:
        return ''

    parser = PageMetaExtractor()
    parser.feed(content)

    tooltip = parser.subtitle.strip() or parser.title.strip()
    # Clean up
    tooltip = re.sub(r'\s+', ' ', tooltip).strip()
    # Escape for HTML attribute
    tooltip = tooltip.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
    return tooltip


def add_tooltips(docs_dir):
    """Process all HTML files and add title attributes to internal links."""
    docs_dir = os.path.normpath(docs_dir)
    modified_count = 0
    link_count = 0

    # Build tooltip cache: relative_path -> tooltip_text
    tooltip_cache = {}

    for root, _dirs, files in os.walk(docs_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, docs_dir)
            tooltip = get_page_tooltip(fpath)
            if tooltip:
                tooltip_cache[rel] = tooltip

    # Pattern: <a href="..." without title="..."
    # Matches <a with href but no title attribute
    link_pattern = re.compile(
        r'(<a\s+)(?![^>]*\btitle\s*=)([^>]*\bhref\s*=\s*"([^"#]*?)"[^>]*>)',
        re.IGNORECASE
    )

    for root, _dirs, files in os.walk(docs_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)

            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except OSError:
                continue

            original = content
            page_dir = os.path.dirname(fpath)

            def add_title(match):
                nonlocal link_count
                prefix = match.group(1)  # "<a "
                rest = match.group(2)    # 'href="..."...>'
                href = match.group(3)    # the href value

                # Skip external links
                if href.startswith(('http', 'mailto:', 'javascript:')):
                    return match.group(0)

                # Skip empty hrefs
                if not href:
                    return match.group(0)

                # Resolve relative path
                target_path = os.path.normpath(os.path.join(page_dir, unquote(href)))
                rel_target = os.path.relpath(target_path, docs_dir)

                tooltip = tooltip_cache.get(rel_target, '')
                if not tooltip:
                    return match.group(0)

                link_count += 1
                return f'{prefix}title="{tooltip}" {rest}'

            content = link_pattern.sub(add_title, content)

            if content != original:
                modified_count += 1
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(content)

    return modified_count, link_count


def main():
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <docs_dir>', file=sys.stderr)
        sys.exit(1)

    docs_dir = sys.argv[1]
    if not os.path.isdir(docs_dir):
        print(f'Error: {docs_dir} is not a directory', file=sys.stderr)
        sys.exit(1)

    modified, links = add_tooltips(docs_dir)
    print(f'Added {links} tooltips across {modified} files')


if __name__ == '__main__':
    main()

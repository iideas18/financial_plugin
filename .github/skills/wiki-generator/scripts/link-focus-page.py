#!/usr/bin/env python3
"""link-focus-page.py — Link a generated focus page back into its L2 parent.

After generating a focus deep-dive page for a specific topic, this script
inserts a visible link card into the parent L2 page so readers can discover it.
It prefers a shared "Deep-Dive Pages" card grid, creating one if needed.

Usage:
    python3 link-focus-page.py <parent_l2_html> <topic_slug> <topic_name> [topic_desc]

Example:
    python3 link-focus-page.py docs/coho_doc/fe/index.html branch-prediction "Branch Prediction Algorithm" "Deep dive into the TAGE predictor and BTB organization."

What it does:
    1. Reads the parent L2 HTML file
    2. Ensures card-grid CSS exists on the page
    3. Finds an existing shared "Deep-Dive Pages" grid and appends a card,
         or creates a new shared grid under the <h2 id="deep-dives"> section
    4. Creates a .bak backup before modifying

The inserted card uses the shared L1/L2 card style:
    <a class="card" href="topic_slug/index.html" title="Topic Name — Deep Dive">
        <h4>Topic Name <span class="focus-badge">Focus</span></h4>
        <p>Topic description</p>
    </a>
"""

import html
import os
import re
import sys


CARD_CSS = """
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem;margin:1rem 0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.2rem;transition:border-color .2s,box-shadow .2s;text-decoration:none;color:inherit;display:block}
.card:hover{border-color:var(--accent);box-shadow:0 4px 12px rgba(0,0,0,.3);text-decoration:none}
.card h4{margin-top:0;color:var(--accent2)}.card p{font-size:.9rem;color:var(--text-muted)}
.card ul{padding-left:1.2rem;font-size:.88rem;color:var(--text-muted)}.card ul li{margin:.25rem 0}
.card .focus-badge{display:inline-block;background:var(--accent4);color:#fff;font-size:.65rem;font-weight:700;padding:1px 7px;border-radius:10px;text-transform:uppercase;letter-spacing:.05em;margin-left:.5rem;vertical-align:middle}
.deep-dive-grid .card .focus-meta{margin-top:.6rem;font-size:.78rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em}
.hub-note{background:var(--surface);border-left:4px solid var(--accent);border-radius:0 8px 8px 0;padding:1rem 1.2rem;margin:1rem 0;color:var(--text-muted)}
""".strip()


def ensure_card_css(content):
    if '.card-grid{' in content and '.focus-badge' in content and '.hub-note{' in content:
        return content

    style_end = re.search(r'</style>', content, re.IGNORECASE)
    if not style_end:
        return content

    return content[:style_end.start()] + CARD_CSS + "\n" + content[style_end.start():]


def build_card_html(link_href, topic_name, topic_desc):
    safe_href = html.escape(link_href, quote=True)
    safe_name = html.escape(topic_name)
    safe_desc = html.escape(topic_desc)
    return (
        f'  <a class="card" href="{safe_href}" title="{safe_name} — Deep Dive">\n'
        f'    <h4>{safe_name} <span class="focus-badge">Focus</span></h4>\n'
        f'    <p>{safe_desc}</p>\n'
        '    <div class="focus-meta">Extracted topic page</div>\n'
        f'  </a>\n'
    )


def insert_into_existing_grid(content, card_html):
    grid_pattern = re.compile(
        r'(<h4[^>]*>\s*Deep-Dive Pages\s*</h4>\s*(?:<p[^>]*class="hub-note"[^>]*>.*?</p>\s*)?<div class="[^"]*card-grid[^"]*">)(.*?)(</div>)',
        re.IGNORECASE | re.DOTALL,
    )
    match = grid_pattern.search(content)
    if not match:
        return None

    return content[:match.start(3)] + card_html + content[match.start(3):]


def create_new_grid_block(card_html):
    return (
        '\n<h4>Deep-Dive Pages</h4>\n'
        '<p class="hub-note">Detailed mechanisms from this page have been extracted into dedicated focus pages. Keep only short summaries here and use the cards below for the full deep dive.</p>\n'
        '<div class="card-grid deep-dive-grid">\n'
        f'{card_html}'
        '</div>\n'
    )


def create_new_section_block(card_html):
    return (
        '\n<h2 id="deep-dives">Deep-Dive Highlights</h2>\n'
        '<p class="hub-note">This page can act as a hub for extracted mechanism pages. When a topic graduates into a focus page, keep a condensed summary here and link to the detailed page below.</p>\n'
        + create_new_grid_block(card_html)
    )


def find_hub_insertion_point(content):
    deep_dives_h2 = re.search(r'<h2[^>]*id="deep-dives"[^>]*>.*?</h2>', content, re.IGNORECASE | re.DOTALL)
    if deep_dives_h2:
        return deep_dives_h2.end()

    footer_match = re.search(r'<div class="footer">', content)
    if footer_match:
        return footer_match.start()

    main_end = content.rfind('</main>')
    if main_end != -1:
        return main_end

    return len(content)


def has_deep_dives_heading(content):
    return re.search(r'<h2[^>]*id="deep-dives"[^>]*>.*?</h2>', content, re.IGNORECASE | re.DOTALL) is not None


def main():
    if len(sys.argv) < 4:
        print("Usage: python3 link-focus-page.py <parent_html> <topic_slug> <topic_name> [topic_desc]")
        sys.exit(1)

    parent_path = sys.argv[1]
    topic_slug = sys.argv[2]
    topic_name = sys.argv[3]
    topic_desc = sys.argv[4] if len(sys.argv) > 4 else f"Detailed deep-dive into {topic_name}."

    if not os.path.isfile(parent_path):
        print(f"ERROR: {parent_path} not found")
        sys.exit(1)

    with open(parent_path, "r", encoding="utf-8") as f:
        content = f.read()

    link_href = f"{topic_slug}/index.html"

    # Check if already linked
    if link_href in content:
        print(f"Already linked: {link_href} found in {parent_path}")
        sys.exit(0)

    content = ensure_card_css(content)
    card_html = build_card_html(link_href, topic_name, topic_desc)

    new_content = insert_into_existing_grid(content, card_html)
    if new_content is None:
        pos = find_hub_insertion_point(content)
        hub_block = create_new_grid_block(card_html) if has_deep_dives_heading(content) else create_new_section_block(card_html)
        new_content = content[:pos] + hub_block + content[pos:]

    # Create backup
    backup_path = parent_path + ".bak"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)

    with open(parent_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Linked: {topic_name}")
    print(f"  Card inserted into shared grid in: {parent_path}")
    print(f"  Points to: {link_href}")
    print(f"  Backup: {backup_path}")


if __name__ == "__main__":
    main()

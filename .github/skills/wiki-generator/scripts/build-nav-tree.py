#!/usr/bin/env python3
"""Build nav-tree.json from the docs directory structure for sidebar navigation.

Usage:
    python3 build-nav-tree.py docs/

Outputs: docs/nav-tree.json

The JSON format is a nested tree:
{
  "label": "Project Name",
  "path": "index.html",
  "children": [
    {
      "label": "Module A",
      "path": "moduleA_doc/index.html",
      "children": [
        {"label": "sub1", "path": "moduleA_doc/sub1/index.html", "children": []},
        ...
      ]
    },
    {"label": "Glossary", "path": "glossary.html", "children": []},
    {"label": "Search",  "path": "search.html",   "children": []}
  ]
}

To inject the sidebar into pages, include this JS snippet in templates (after nav-tree.json exists):

  <script>
  (function(){
    var xhr=new XMLHttpRequest();
    xhr.open('GET','{RELATIVE_PATH_TO}nav-tree.json',true);
    xhr.onload=function(){
      if(xhr.status!==200)return;
      var tree;try{tree=JSON.parse(xhr.responseText);}catch(e){return;}
      var nav=document.createElement('nav');
      nav.className='sidebar';nav.setAttribute('aria-label','Wiki navigation');
      nav.innerHTML='<button class="sidebar-toggle" aria-label="Toggle sidebar">&#9776;</button>'+buildList(tree,'');
      document.body.insertBefore(nav,document.body.firstChild);
      nav.querySelector('.sidebar-toggle').addEventListener('click',function(){nav.classList.toggle('open');});
    };
    xhr.send();
    function buildList(node,base){
      var html='<ul>';
      if(node.path)html+='<li><a href="'+base+node.path+'">'+node.label+'</a>';
      if(node.children&&node.children.length){
        html+='<ul>';
        node.children.forEach(function(c){html+='<li><a href="'+base+c.path+'">'+c.label+'</a>';
          if(c.children&&c.children.length){html+=buildList_children(c.children,base);}
          html+='</li>';
        });
        html+='</ul>';
      }
      if(node.path)html+='</li>';
      html+='</ul>';return html;
    }
    function buildList_children(children,base){
      var html='<ul>';
      children.forEach(function(c){html+='<li><a href="'+base+c.path+'">'+c.label+'</a>';
        if(c.children&&c.children.length)html+=buildList_children(c.children,base);
        html+='</li>';});
      return html+'</ul>';
    }
  })();
  </script>
"""

import json
import os
import re
import sys
from html.parser import HTMLParser


class TitleExtractor(HTMLParser):
    """Extract <title> text from HTML."""
    def __init__(self):
        super().__init__()
        self._in_title = False
        self.title = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def get_title(filepath):
    """Get page title from HTML file, falling back to directory name."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read(4096)  # Title is always near the top
    except OSError:
        return os.path.basename(os.path.dirname(filepath))

    parser = TitleExtractor()
    parser.feed(content)
    title = parser.title.strip()

    # Clean up common patterns: "Module — Subtitle" -> "Module"
    if ' — ' in title:
        title = title.split(' — ')[0].strip()
    if ' - ' in title:
        title = title.split(' - ')[0].strip()

    return title or os.path.basename(os.path.dirname(filepath))


def build_tree(docs_dir):
    """Build navigation tree from docs directory structure."""
    docs_dir = os.path.normpath(docs_dir)
    root_index = os.path.join(docs_dir, 'index.html')

    root_label = 'Wiki'
    if os.path.isfile(root_index):
        root_label = get_title(root_index)

    root = {
        'label': root_label,
        'path': 'index.html',
        'children': []
    }

    # Collect module directories (those containing index.html)
    entries = sorted(os.listdir(docs_dir))
    for entry in entries:
        entry_path = os.path.join(docs_dir, entry)

        # Top-level HTML files (glossary, search)
        if os.path.isfile(entry_path) and entry.endswith('.html'):
            if entry in ('index.html', 'search.html'):
                continue
            label = entry.replace('.html', '').replace('_', ' ').title()
            root['children'].append({
                'label': label,
                'path': entry,
                'children': []
            })
            continue

        if not os.path.isdir(entry_path):
            continue

        # Skip hidden dirs, _style-spec, etc.
        if entry.startswith(('.', '_')):
            continue

        mod_index = os.path.join(entry_path, 'index.html')
        if not os.path.isfile(mod_index):
            continue

        mod_label = get_title(mod_index)
        mod_node = {
            'label': mod_label,
            'path': f'{entry}/index.html',
            'children': []
        }

        # Check for sub-module directories
        try:
            sub_entries = sorted(os.listdir(entry_path))
        except OSError:
            sub_entries = []

        for sub in sub_entries:
            sub_path = os.path.join(entry_path, sub)
            if not os.path.isdir(sub_path):
                continue
            if sub.startswith(('.', '_')):
                continue
            sub_index = os.path.join(sub_path, 'index.html')
            if not os.path.isfile(sub_index):
                continue

            sub_label = get_title(sub_index)
            mod_node['children'].append({
                'label': sub_label,
                'path': f'{entry}/{sub}/index.html',
                'children': []
            })

        root['children'].append(mod_node)

    # Add search at the end if search.html exists
    if os.path.isfile(os.path.join(docs_dir, 'search.html')):
        root['children'].append({
            'label': 'Search',
            'path': 'search.html',
            'children': []
        })

    return root


def main():
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <docs_dir>', file=sys.stderr)
        sys.exit(1)

    docs_dir = sys.argv[1]
    if not os.path.isdir(docs_dir):
        print(f'Error: {docs_dir} is not a directory', file=sys.stderr)
        sys.exit(1)

    tree = build_tree(docs_dir)
    out_path = os.path.join(docs_dir, 'nav-tree.json')

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(tree, f, indent=2, ensure_ascii=False)

    # Count nodes
    def count_nodes(node):
        c = 1
        for child in node.get('children', []):
            c += count_nodes(child)
        return c

    total = count_nodes(tree)
    print(f'Built nav tree: {total} nodes -> {out_path}')


if __name__ == '__main__':
    main()

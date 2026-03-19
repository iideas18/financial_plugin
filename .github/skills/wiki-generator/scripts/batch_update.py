#!/usr/bin/env python3
"""
Batch update script for module-wiki HTML pages.

Copy this script into the target docs folder, customize the transformations
below, run it, then delete it.

Usage:
    cp batch_update.py docs/<module>_doc/
    cd docs/<module>_doc/
    python3 batch_update.py
    rm batch_update.py

This script demonstrates common transformations. Enable/disable each one
by setting the flag to True/False below.
"""

import os
import re
import glob

# ──────────────────────────────────────────────────────────────
# CONFIGURATION — set True/False to enable/disable each fix
# ──────────────────────────────────────────────────────────────

# Fix 1: Remove `color: var(--text)` from `pre code` CSS rule
# (prevents highlight.js token colors from being overridden)
FIX_PRE_CODE_COLOR = True

# Fix 2: Change diagram-container background from #fff to var(--bg)
FIX_DIAGRAM_BG = True

# Fix 3: Add light theme CSS variables + overrides
ADD_LIGHT_THEME = True

# Fix 4: Change startOnLoad:true to startOnLoad:false
FIX_START_ON_LOAD = True

# Fix 5: Add highlight.js CDN links
ADD_HLJS = True

# Fix 6: Add theme toggle button
ADD_TOGGLE_BUTTON = True

# Fix 7: Replace footer JS with full theme-aware version
# (includes data-source mermaid preservation, textContent restore,
#  highlight.js theme switching, localStorage persistence)
REPLACE_FOOTER_JS = True

# Fix 8: Add language-xxx class to <code> blocks inside <pre>
ADD_LANG_CLASS = True
CODE_LANGUAGE = "cpp"  # Change to "python", "typescript", "java", etc.

# Fix 9: Remove hardcoded Mermaid `style` lines
REMOVE_MERMAID_STYLES = True

# localStorage key for theme (e.g., "coho", "mymodule")
THEME_KEY = "module"  # Customize this!


# ──────────────────────────────────────────────────────────────
# LIGHT THEME CSS BLOCK (injected after dark theme CSS)
# ──────────────────────────────────────────────────────────────
LIGHT_THEME_CSS = """
/* === Light theme === */
[data-theme="light"]{--bg:#ffffff;--surface:#f6f8fa;--border:#d0d7de;--text:#1f2328;--text-muted:#656d76;--accent:#0969da;--accent2:#1a7f37;--accent3:#9a6700;--accent4:#cf222e;--heading:#1f2328;--code-bg:#f6f8fa;--table-even:#f6f8fa;--table-odd:#ffffff}
[data-theme="light"] .hero{background:linear-gradient(135deg,#f0f4f8 0%,#ffffff 100%)}
[data-theme="light"] .badge{color:#fff}
[data-theme="light"] .card:hover{box-shadow:0 4px 12px rgba(0,0,0,.08)}
/* === Theme toggle button === */
.theme-toggle{position:fixed;top:1rem;right:1rem;z-index:1000;background:var(--surface);border:1px solid var(--border);border-radius:50%;width:40px;height:40px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.2rem;color:var(--text);transition:background .2s,border-color .2s;box-shadow:0 2px 8px rgba(0,0,0,.15)}
.theme-toggle:hover{border-color:var(--accent)}
"""

# ──────────────────────────────────────────────────────────────
# FOOTER JS (full theme-aware version)
# ──────────────────────────────────────────────────────────────
def make_footer_js(theme_key):
    return f"""<script>
document.querySelectorAll('pre.mermaid').forEach(function(el){{
  if(!el.getAttribute('data-source')) el.setAttribute('data-source',el.textContent);
}});
(function(){{
  var btn=document.getElementById('themeToggle');
  var hljsLink=document.getElementById('hljs-theme');
  var darkHL='https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css';
  var lightHL='https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
  function renderMermaid(t){{
    var nodes=document.querySelectorAll('pre.mermaid');
    if(!nodes.length||!window.mermaid) return;
    nodes.forEach(function(el){{
      var src=el.getAttribute('data-source');
      if(src){{ el.removeAttribute('data-processed'); el.textContent=src; }}
    }});
    try{{mermaid.initialize({{startOnLoad:false,theme:(t==='light')?'default':'dark',flowchart:{{useMaxWidth:true,htmlLabels:true,curve:'basis'}}}});mermaid.run();}}catch(e){{}}
  }}
  function applyTheme(t){{
    document.documentElement.setAttribute('data-theme',t);
    hljsLink.href=(t==='light')?lightHL:darkHL;
    btn.innerHTML=(t==='light')?'\\u2600':'\\u263E';
    localStorage.setItem('{theme_key}-theme',t);
    renderMermaid(t);
  }}
  var saved=localStorage.getItem('{theme_key}-theme')||(window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
  applyTheme(saved);
  btn.addEventListener('click',function(){{applyTheme(document.documentElement.getAttribute('data-theme')==='light'?'dark':'light');}});
}})();
hljs.highlightAll();
</script>"""


# ──────────────────────────────────────────────────────────────
# PROCESSING
# ──────────────────────────────────────────────────────────────
def process_file(path, theme_key):
    with open(path, 'r') as f:
        html = f.read()
    original = html
    changes = []

    # Fix 1: pre code color override
    if FIX_PRE_CODE_COLOR:
        new_html = re.sub(
            r'pre code\s*\{[^}]*color:\s*var\(--text\)[^}]*\}',
            'pre code{background:none;padding:0}',
            html
        )
        if new_html != html:
            html = new_html
            changes.append('pre-code-fix')

    # Fix 2: diagram-container background
    if FIX_DIAGRAM_BG:
        new_html = html.replace(
            'diagram-container{background:#fff',
            'diagram-container{background:var(--bg)'
        ).replace(
            'diagram-container { background: #fff',
            'diagram-container { background: var(--bg)'
        )
        if new_html != html:
            html = new_html
            changes.append('diagram-bg')

    # Fix 3: Light theme CSS
    if ADD_LIGHT_THEME and 'data-theme="light"' not in html:
        html = html.replace('</style>', LIGHT_THEME_CSS + '\n</style>')
        changes.append('light-theme-css')

    # Fix 4: startOnLoad
    if FIX_START_ON_LOAD:
        new_html = html.replace('startOnLoad:true', 'startOnLoad:false')
        if new_html != html:
            html = new_html
            changes.append('startOnLoad')

    # Fix 5: Highlight.js CDN
    if ADD_HLJS and 'hljs' not in html:
        hljs_block = (
            '<link id="hljs-theme" rel="stylesheet" '
            'href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css">\n'
            '<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>\n'
        )
        html = html.replace('</head>', hljs_block + '</head>')
        changes.append('hljs')

    # Fix 6: Toggle button
    if ADD_TOGGLE_BUTTON and 'themeToggle' not in html:
        html = html.replace(
            '<body>',
            '<body>\n<button class="theme-toggle" id="themeToggle" title="Toggle light/dark theme">&#9790;</button>'
        )
        changes.append('toggle-btn')

    # Fix 7: Footer JS
    if REPLACE_FOOTER_JS:
        new_js = make_footer_js(theme_key)
        # Replace existing <script> ... </script> block before </body>
        new_html = re.sub(
            r'<script>\s*(?://.*\n)*\s*\(function\(\)\{.*?</script>',
            new_js,
            html,
            flags=re.DOTALL
        )
        if new_html != html:
            html = new_html
            changes.append('footer-js-replaced')
        elif 'data-source' not in html:
            # No existing footer JS — inject before </body>
            html = html.replace('</body>', new_js + '\n</body>')
            changes.append('footer-js-added')

    # Fix 8: language class on code blocks
    if ADD_LANG_CLASS:
        lang_class = f'language-{CODE_LANGUAGE}'
        new_html = re.sub(
            r'<pre><code(?!\s+class="language-)>',
            f'<pre><code class="{lang_class}">',
            html
        )
        if new_html != html:
            html = new_html
            changes.append('lang-cpp')

    # Fix 9: Remove hardcoded Mermaid style lines
    if REMOVE_MERMAID_STYLES:
        new_html = re.sub(
            r'\n\s*style\s+\w+\s+fill:#[0-9a-fA-F]+[^\n]*',
            '',
            html
        )
        if new_html != html:
            html = new_html
            changes.append('mermaid-styles-removed')

    if html != original:
        with open(path, 'w') as f:
            f.write(html)
        return changes
    return []


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    patterns = [
        os.path.join(script_dir, 'index.html'),
        os.path.join(script_dir, '*/index.html'),
    ]
    files = []
    for pattern in patterns:
        files.extend(glob.glob(pattern))
    files = sorted(set(files))

    print(f"Found {len(files)} HTML files")
    for path in files:
        changes = process_file(path, THEME_KEY)
        rel = os.path.relpath(path, script_dir)
        if changes:
            print(f"  {rel}: {', '.join(changes)}")
        else:
            print(f"  {rel}: (no changes needed)")
    print("Done.")


if __name__ == '__main__':
    main()

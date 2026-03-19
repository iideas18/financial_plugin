#!/usr/bin/env python3
"""
web_selector.py — Lightweight web UI for batch stock selection & analysis.

Zero extra dependencies — uses only Python stdlib + run_analysis.py.

Usage:
    python web_selector.py                  # default port 8686
    python web_selector.py --port 9090      # custom port
    python web_selector.py --out-dir /tmp   # custom output directory
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from functools import lru_cache
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote

_SCRIPTS_DIR = Path(__file__).parent
_SYM_FILE = _SCRIPTS_DIR / "data" / "a_share_symbols.csv"
sys.path.insert(0, str(_SCRIPTS_DIR))
from proxy_config import apply_proxy, configure_proxy, get_proxy_info, test_proxy
apply_proxy()  # configure proxy before any network calls

# ── globals set by CLI ──────────────────────────────────────────────────────
OUT_DIR: str = "."


@lru_cache(maxsize=1)
def _load_stocks() -> list[dict]:
    """Read the local CSV and return [{code, name}, ...].  Cached after first call."""
    stocks = []
    with open(_SYM_FILE, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stocks.append({"code": row["code"].strip(), "name": row["name"].strip()})
    return stocks


@lru_cache(maxsize=1)
def _stocks_json() -> str:
    """Pre-serialised stock list for embedding in HTML."""
    return json.dumps(_load_stocks(), ensure_ascii=False)


# ── Markdown → HTML (zero-dependency) ───────────────────────────────────────
def _md_to_html(md_text: str) -> str:
    """Convert markdown to HTML with basic formatting support."""
    # Strip YAML frontmatter
    md_text = re.sub(r'^---\n.*?\n---\n', '', md_text, count=1, flags=re.DOTALL)
    lines = md_text.split('\n')
    html_parts: list[str] = []
    in_table = False
    in_code = False
    in_ul = False
    i = 0
    while i < len(lines):
        line = lines[i]
        # Fenced code block
        if line.strip().startswith('```'):
            if in_code:
                html_parts.append('</code></pre>')
                in_code = False
            else:
                lang = line.strip()[3:].strip()
                html_parts.append(f'<pre><code class="lang-{lang}">' if lang else '<pre><code>')
                in_code = True
            i += 1
            continue
        if in_code:
            html_parts.append(_esc(line))
            html_parts.append('\n')
            i += 1
            continue
        # Close open list if needed
        if in_ul and not re.match(r'^\s*[-*]\s', line):
            html_parts.append('</ul>')
            in_ul = False
        # Empty line
        if not line.strip():
            if in_table:
                html_parts.append('</tbody></table>')
                in_table = False
            i += 1
            continue
        # Headers
        hm = re.match(r'^(#{1,6})\s+(.*)', line)
        if hm:
            lvl = len(hm.group(1))
            html_parts.append(f'<h{lvl}>{_inline(hm.group(2))}</h{lvl}>')
            i += 1
            continue
        # Table
        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if not in_table:
                # Check if next line is separator
                if i + 1 < len(lines) and re.match(r'^[\s|:-]+$', lines[i + 1]):
                    html_parts.append('<table><thead><tr>')
                    for c in cells:
                        html_parts.append(f'<th>{_inline(c)}</th>')
                    html_parts.append('</tr></thead><tbody>')
                    in_table = True
                    i += 2  # skip separator line
                    continue
                else:
                    html_parts.append('<table><tbody>')
                    in_table = True
            # Skip separator rows
            if re.match(r'^[\s|:-]+$', line):
                i += 1
                continue
            html_parts.append('<tr>')
            for c in cells:
                html_parts.append(f'<td>{_inline(c)}</td>')
            html_parts.append('</tr>')
            i += 1
            continue
        # Close table if open but line has no pipes
        if in_table:
            html_parts.append('</tbody></table>')
            in_table = False
        # Blockquote
        if line.startswith('>'):
            html_parts.append(f'<blockquote>{_inline(line[1:].strip())}</blockquote>')
            i += 1
            continue
        # Unordered list
        lm = re.match(r'^(\s*)[-*]\s+(.*)', line)
        if lm:
            if not in_ul:
                html_parts.append('<ul>')
                in_ul = True
            html_parts.append(f'<li>{_inline(lm.group(2))}</li>')
            i += 1
            continue
        # Horizontal rule
        if re.match(r'^[-*_]{3,}\s*$', line):
            html_parts.append('<hr>')
            i += 1
            continue
        # Paragraph
        html_parts.append(f'<p>{_inline(line)}</p>')
        i += 1
    if in_table:
        html_parts.append('</tbody></table>')
    if in_ul:
        html_parts.append('</ul>')
    if in_code:
        html_parts.append('</code></pre>')
    return '\n'.join(html_parts)


def _esc(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _inline(text: str) -> str:
    """Handle inline markdown: bold, italic, code, links, images."""
    # Images ![alt](src) — rewrite relative paths
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',
                  lambda m: f'<img src="/files/{m.group(2)}" alt="{_esc(m.group(1))}" style="max-width:100%">',
                  text)
    # Links [text](url)
    text = re.sub(r'\[([^\]]*)\]\(([^)]+)\)',
                  lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    # Inline code
    text = re.sub(r'`([^`]+)`', lambda m: f'<code>{_esc(m.group(1))}</code>', text)
    # Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    # Italic *text* or _text_
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'(?<![\w])_(.+?)_(?![\w])', r'<em>\1</em>', text)
    return text


def _report_viewer_page(title: str, body_html: str, filename: str) -> str:
    """Full HTML page wrapping a rendered markdown report."""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>
  :root{{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;
    --text2:#8b949e;--accent:#58a6ff;--green:#3fb950;--red:#f85149;--radius:8px}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
    background:var(--bg);color:var(--text);line-height:1.6}}
  .toolbar{{background:var(--surface);border-bottom:1px solid var(--border);padding:10px 20px;
    display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}}
  .toolbar a{{color:var(--accent);text-decoration:none;font-size:14px}}
  .toolbar a:hover{{text-decoration:underline}}
  .toolbar .title{{font-weight:600;font-size:14px;color:var(--text);margin-left:8px;flex:1}}
  .toolbar .dl-btn{{padding:4px 12px;border-radius:4px;border:1px solid var(--border);
    background:transparent;color:var(--text2);cursor:pointer;font-size:12px}}
  .toolbar .dl-btn:hover{{border-color:var(--accent);color:var(--text)}}
  .content{{max-width:960px;margin:0 auto;padding:24px 20px}}
  h1{{font-size:1.5rem;margin:20px 0 12px;border-bottom:1px solid var(--border);padding-bottom:8px}}
  h2{{font-size:1.25rem;margin:24px 0 10px;border-bottom:1px solid var(--border);padding-bottom:6px}}
  h3{{font-size:1.1rem;margin:18px 0 8px}}
  p{{margin:8px 0}}
  blockquote{{border-left:3px solid var(--accent);padding:6px 16px;margin:12px 0;color:var(--text2);
    background:rgba(88,166,255,.05);border-radius:0 var(--radius) var(--radius) 0}}
  table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}}
  th,td{{padding:8px 12px;border:1px solid var(--border);text-align:left}}
  th{{background:var(--surface);font-weight:600}}
  tr:hover{{background:rgba(88,166,255,.04)}}
  code{{font-family:'SF Mono',SFMono-Regular,Consolas,monospace;font-size:13px;
    background:var(--surface);padding:2px 6px;border-radius:4px}}
  pre{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
    padding:12px 16px;overflow-x:auto;margin:12px 0}}
  pre code{{background:none;padding:0}}
  ul{{margin:8px 0 8px 24px}}
  li{{margin:4px 0}}
  img{{border-radius:var(--radius);border:1px solid var(--border);margin:12px 0}}
  a{{color:var(--accent)}}
  strong{{color:var(--text)}}
  em{{color:var(--text2)}}
  hr{{border:none;border-top:1px solid var(--border);margin:20px 0}}
</style>
</head>
<body>
<div class="toolbar">
  <a href="/">← Back to Selector</a>
  <a href="/reports">Reports</a>
  <span class="title">{_esc(filename)}</span>
  <a class="dl-btn" href="/files/{filename}" download>⬇ Download</a>
</div>
<div class="content">
{body_html}
</div>
</body>
</html>"""


def _reports_list_page(files: list[dict]) -> str:
    """HTML page listing all available reports."""
    rows = ''
    for f in files:
        icon = '📊' if f['type'] == 'chart' else '📋'
        view_link = f'/view/{f["name"]}' if f['type'] != 'chart' else f'/files/{f["name"]}'
        rows += f"""<tr>
          <td>{icon}</td>
          <td><a href="{view_link}">{_esc(f['name'])}</a></td>
          <td>{_esc(f['type'])}</td>
          <td>{_esc(f['size'])}</td>
          <td>{_esc(f['mtime'])}</td>
          <td><a href="/files/{f['name']}" download>⬇</a></td>
        </tr>\n"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reports — K-Line Analysis</title>
<style>
  :root{{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;
    --text2:#8b949e;--accent:#58a6ff;--green:#3fb950;--radius:8px}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
    background:var(--bg);color:var(--text);line-height:1.5}}
  .container{{max-width:1100px;margin:0 auto;padding:20px}}
  .toolbar{{background:var(--surface);border-bottom:1px solid var(--border);padding:10px 20px;
    display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:10}}
  .toolbar a{{color:var(--accent);text-decoration:none;font-size:14px}}
  .toolbar a:hover{{text-decoration:underline}}
  h1{{font-size:1.4rem;margin:16px 0;display:flex;align-items:center;gap:8px}}
  table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}}
  th,td{{padding:8px 12px;border:1px solid var(--border);text-align:left}}
  th{{background:var(--surface);font-weight:600}}
  tr:hover{{background:rgba(88,166,255,.04)}}
  a{{color:var(--accent)}}
  .empty{{padding:40px;text-align:center;color:var(--text2)}}
</style>
</head>
<body>
<div class="toolbar">
  <a href="/">← Back to Selector</a>
  <span style="flex:1"></span>
  <span style="color:var(--text2);font-size:13px">{len(files)} file(s)</span>
</div>
<div class="container">
  <h1>📂 Analysis Reports</h1>
  {'<table><thead><tr><th></th><th>File</th><th>Type</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>' if rows else '<div class="empty">No reports found. Run an analysis first.</div>'}
</div>
</body>
</html>"""


def _list_report_files() -> list[dict]:
    """Scan output directory for report files."""
    out_dir = Path(OUT_DIR).resolve()
    files = []
    for ext in ('*.md', '*.txt', '*.png'):
        for p in sorted(out_dir.glob(ext), key=lambda p: p.stat().st_mtime, reverse=True):
            if p.name == 'README.md':
                continue
            st = p.stat()
            if ext == '*.png':
                ftype = 'chart'
            elif ext == '*.md':
                ftype = 'markdown'
            else:
                ftype = 'text'
            size = st.st_size
            if size < 1024:
                size_str = f'{size} B'
            elif size < 1024 * 1024:
                size_str = f'{size/1024:.1f} KB'
            else:
                size_str = f'{size/1024/1024:.1f} MB'
            files.append({
                'name': p.name,
                'type': ftype,
                'size': size_str,
                'mtime': datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'),
            })
    return files


# ── HTML template (embedded) ────────────────────────────────────────────────
_html_cache: str | None = None

def _html_page() -> str:
    global _html_cache
    if _html_cache is None:
        _html_cache = _build_html_page()
    return _html_cache

def _build_html_page() -> str:
    stocks_inline = _stocks_json()
    return r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock Selector — K-Line Analysis</title>
<style>
  :root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;
    --text2:#8b949e;--accent:#58a6ff;--accent2:#1f6feb;--green:#3fb950;
    --red:#f85149;--orange:#d29922;--radius:8px}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
    background:var(--bg);color:var(--text);line-height:1.5;min-height:100vh}
  .container{max-width:1200px;margin:0 auto;padding:20px}
  h1{font-size:1.4rem;font-weight:600;margin-bottom:16px;display:flex;align-items:center;gap:8px}
  h1 span.icon{font-size:1.6rem}

  /* Layout */
  .main{display:grid;grid-template-columns:1fr 340px;gap:16px}
  @media(max-width:800px){.main{grid-template-columns:1fr}}

  /* Panels */
  .panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px}
  .panel h2{font-size:1rem;font-weight:600;margin-bottom:12px;color:var(--text)}

  /* Search */
  .search-row{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
  .search-row input{flex:1;min-width:200px;padding:8px 12px;border-radius:6px;border:1px solid var(--border);
    background:var(--bg);color:var(--text);font-size:14px;outline:none}
  .search-row input:focus{border-color:var(--accent)}

  /* Filter tabs */
  .tabs{display:flex;gap:4px;margin-bottom:12px;flex-wrap:wrap}
  .tabs button{padding:4px 14px;border-radius:20px;border:1px solid var(--border);
    background:transparent;color:var(--text2);cursor:pointer;font-size:13px;transition:.15s}
  .tabs button:hover{border-color:var(--accent);color:var(--text)}
  .tabs button.active{background:var(--accent2);border-color:var(--accent2);color:#fff}

  /* Stock list */
  .stock-list{height:520px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;background:var(--bg)}
  .stock-list::-webkit-scrollbar{width:6px}
  .stock-list::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
  .stock-item{display:flex;align-items:center;padding:6px 12px;cursor:pointer;transition:background .1s;border-bottom:1px solid var(--border)}
  .stock-item:hover{background:#1c2333}
  .stock-item.checked{background:#1a2332}
  .stock-item input[type=checkbox]{accent-color:var(--accent);width:16px;height:16px;cursor:pointer}
  .stock-item .code{font-family:'SF Mono',SFMono-Regular,Consolas,monospace;font-size:13px;
    width:70px;margin-left:10px;color:var(--accent)}
  .stock-item .name{font-size:13px;color:var(--text);margin-left:8px}
  .stock-item .market-tag{font-size:11px;padding:1px 6px;border-radius:10px;margin-left:auto;
    background:var(--border);color:var(--text2)}
  .count-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-size:13px;color:var(--text2)}
  .count-bar .total{color:var(--text2)}
  .batch-btns button{padding:3px 10px;border-radius:4px;border:1px solid var(--border);
    background:transparent;color:var(--text2);cursor:pointer;font-size:12px;margin-left:4px}
  .batch-btns button:hover{border-color:var(--accent);color:var(--text)}

  /* Right panel — selected */
  .selected-panel{display:flex;flex-direction:column}
  .selected-list{flex:1;overflow-y:auto;max-height:260px;margin-bottom:12px}
  .selected-chip{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;margin:3px;
    border-radius:16px;background:var(--accent2);color:#fff;font-size:12px;cursor:default}
  .selected-chip .remove{cursor:pointer;opacity:.7;font-weight:bold}
  .selected-chip .remove:hover{opacity:1}

  /* Options */
  .options{display:flex;flex-direction:column;gap:10px;margin-bottom:16px}
  .options label{font-size:13px;color:var(--text2)}
  .options select{padding:6px 10px;border-radius:6px;border:1px solid var(--border);
    background:var(--bg);color:var(--text);font-size:13px}

  /* Run button */
  .run-btn{width:100%;padding:10px;border-radius:6px;border:none;
    background:var(--green);color:#fff;font-size:15px;font-weight:600;cursor:pointer;transition:.15s}
  .run-btn:hover{filter:brightness(1.1)}
  .run-btn:disabled{opacity:.5;cursor:not-allowed}

  /* Results */
  .results{margin-top:16px}
  .result-log{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:12px;
    font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:300px;overflow-y:auto;color:var(--text2)}
  .result-log .ok{color:var(--green)}
  .result-log .err{color:var(--red)}
  .result-log .info{color:var(--accent)}
  .result-log a{color:var(--accent);text-decoration:underline}

  /* Progress */
  .progress-bar{height:4px;background:var(--border);border-radius:2px;margin-bottom:8px;overflow:hidden}
  .progress-bar .fill{height:100%;background:var(--accent);transition:width .3s}

  .empty-msg{padding:40px;text-align:center;color:var(--text2);font-size:13px}

  /* Sector scan */
  .scan-section{margin-top:16px;border-top:1px solid var(--border);padding-top:16px}
  .scan-section h2{font-size:1rem;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:6px}
  .scan-btn{width:100%;padding:8px;border-radius:6px;border:none;
    background:var(--orange);color:#fff;font-size:14px;font-weight:600;cursor:pointer;transition:.15s;margin-bottom:8px}
  .scan-btn:hover{filter:brightness(1.1)}
  .scan-btn:disabled{opacity:.5;cursor:not-allowed}
  .scan-opts{display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap}
  .scan-opts select{padding:4px 8px;border-radius:4px;border:1px solid var(--border);
    background:var(--bg);color:var(--text);font-size:12px}
  .scan-result{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:12px;
    font-size:12px;max-height:400px;overflow-y:auto;display:none}
  .scan-result table{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0}
  .scan-result th,.scan-result td{padding:4px 8px;border:1px solid var(--border);text-align:left}
  .scan-result th{background:var(--surface);font-weight:600;white-space:nowrap}
  .scan-result td{white-space:nowrap}
  .scan-result .pos{color:var(--red)}
  .scan-result .neg{color:var(--green)}
  .scan-result h3{font-size:13px;margin:10px 0 4px;color:var(--accent)}
  .scan-result .board-link{color:var(--accent);cursor:pointer;text-decoration:underline}
  .scan-result .add-btn{padding:1px 6px;border-radius:3px;border:1px solid var(--border);
    background:transparent;color:var(--accent);cursor:pointer;font-size:11px}
  .scan-result .add-btn:hover{background:var(--accent2);color:#fff;border-color:var(--accent2)}

  /* Proxy settings */
  .proxy-section{margin-top:16px;border-top:1px solid var(--border);padding-top:16px}
  .proxy-section h2{font-size:1rem;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:6px}
  .proxy-row{display:flex;gap:6px;margin-bottom:8px;align-items:center}
  .proxy-row input{flex:1;padding:5px 8px;border-radius:4px;border:1px solid var(--border);
    background:var(--bg);color:var(--text);font-size:12px;font-family:monospace}
  .proxy-row button{padding:5px 12px;border-radius:4px;border:1px solid var(--border);
    background:var(--surface);color:var(--text);cursor:pointer;font-size:12px;white-space:nowrap}
  .proxy-row button:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
  .proxy-status{font-size:11px;color:var(--text2);margin-bottom:4px}
  .proxy-result{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px 12px;
    font-size:11px;font-family:monospace;margin-top:6px;display:none;max-height:200px;overflow-y:auto}
  .proxy-ok{color:var(--green)}.proxy-fail{color:var(--red)}
</style>
</head>
<body>
<div class="container">
  <h1><span class="icon">📊</span> Stock Selector — K-Line Analysis</h1>
  <div class="main">
    <!-- Left: stock list -->
    <div class="panel">
      <div class="search-row">
        <input id="search" type="text" placeholder="Search by code or name... (e.g. 000063 or 中兴)">
      </div>
      <div class="tabs" id="tabs">
        <button class="active" data-filter="all">All</button>
        <button data-filter="sh">沪市 SH</button>
        <button data-filter="sz">深市 SZ</button>
        <button data-filter="cy">创业板 CYB</button>
        <button data-filter="selected">✓ Selected</button>
      </div>
      <div class="count-bar">
        <span id="showCount" class="total"></span>
        <span class="batch-btns">
          <button onclick="selectAllVisible()">Select visible</button>
          <button onclick="deselectAll()">Clear all</button>
        </span>
      </div>
      <div class="stock-list" id="stockList"></div>
    </div>

    <!-- Right: selected & options -->
    <div class="panel selected-panel">
      <h2>Selected (<span id="selCount">0</span>)</h2>
      <div class="selected-list" id="selectedList"></div>

      <div class="options">
        <label>Analysis Mode
          <select id="optMode">
            <option value="structured">Structured</option>
            <option value="full" selected>Full</option>
            <option value="execution">Execution</option>
          </select>
        </label>
        <label>Output Format
          <select id="optFormat">
            <option value="markdown" selected>Markdown</option>
            <option value="text">Text</option>
            <option value="both">Both</option>
          </select>
        </label>
      </div>

      <div style="display:flex;gap:8px">
        <button class="run-btn" id="runBtn" onclick="runAnalysis()" style="flex:1">▶ Run Analysis</button>
        <a href="/reports" target="_blank" class="run-btn" style="flex:0;padding:10px 16px;background:var(--accent2);text-decoration:none;text-align:center;border-radius:6px;font-size:14px;font-weight:600;color:#fff">📂 Reports</a>
      </div>

      <div class="results" id="results" style="display:none">
        <div class="progress-bar"><div class="fill" id="progressFill" style="width:0%"></div></div>
        <div class="result-log" id="resultLog"></div>
      </div>

      <!-- Proxy Settings Section -->
      <div class="proxy-section">
        <h2>&#9881; Proxy Settings</h2>
        <div class="proxy-status" id="proxyStatus">Loading...</div>
        <div class="proxy-row">
          <input type="text" id="proxyUrl" placeholder="http://child-prc.intel.com:913">
          <button onclick="saveProxy()">Save</button>
          <button onclick="testProxy()">Test</button>
        </div>
        <div class="proxy-result" id="proxyResult"></div>
      </div>

      <!-- Sector Scan Section -->
      <div class="scan-section">
        <h2>🔍 Sector Scan — Leading Groups</h2>
        <div class="scan-opts">
          <select id="scanType">
            <option value="all">All (Industry + Concept + Fund Flow)</option>
            <option value="industry">Industry Boards 行业板块</option>
            <option value="concept">Concept Boards 概念板块</option>
            <option value="fund-flow">Fund Flow 资金流</option>
          </select>
          <select id="scanTop">
            <option value="10" selected>Top 10</option>
            <option value="20">Top 20</option>
            <option value="30">Top 30</option>
          </select>
        </div>
        <button class="scan-btn" id="scanBtn" onclick="runSectorScan()">📡 Scan Leading Groups</button>
        <div class="scan-result" id="scanResult"></div>
      </div>
    </div>
  </div>
</div>

<script>
const ALL_STOCKS = """ + stocks_inline + r""";
let selected = new Set();
let currentFilter = 'all';
let _filtered = ALL_STOCKS;  // cached filtered list

const ROW_H = 37;  // px per item
const OVERSCAN = 6;

// ── Init ─────────────────────────────────────────────────────────────────
refilter();
render();

// ── Filtering ────────────────────────────────────────────────────────────
function getMarket(code) {
  if (code.startsWith('6')) return 'sh';
  if (code.startsWith('3')) return 'cy';
  if (code.startsWith('0')) return 'sz';
  return 'other';
}

function refilter() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  _filtered = ALL_STOCKS.filter(s => {
    if (currentFilter === 'sh' && getMarket(s.code) !== 'sh') return false;
    if (currentFilter === 'sz' && getMarket(s.code) !== 'sz') return false;
    if (currentFilter === 'cy' && getMarket(s.code) !== 'cy') return false;
    if (currentFilter === 'selected' && !selected.has(s.code)) return false;
    if (q && !s.code.includes(q) && !s.name.toLowerCase().includes(q)) return false;
    return true;
  });
}

// ── Virtual-scroll render ─────────────────────────────────────────────────
function render() {
  const list = document.getElementById('stockList');
  document.getElementById('showCount').textContent = `Showing ${_filtered.length} / ${ALL_STOCKS.length}`;

  const totalH = _filtered.length * ROW_H;
  // spacer + viewport container
  list.innerHTML = `<div id="vSpace" style="height:${totalH}px;position:relative"></div>`;
  renderVisible();
  renderSelectedChips();
}

function renderVisible() {
  const list = document.getElementById('stockList');
  const space = document.getElementById('vSpace');
  if (!space) return;
  const scrollTop = list.scrollTop;
  const viewH = list.clientHeight;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_H) - OVERSCAN);
  const endIdx = Math.min(_filtered.length, Math.ceil((scrollTop + viewH) / ROW_H) + OVERSCAN);

  // Remove old rows
  const old = space.querySelector('.vRows');
  if (old) old.remove();

  const wrap = document.createElement('div');
  wrap.className = 'vRows';
  wrap.style.position = 'absolute';
  wrap.style.top = (startIdx * ROW_H) + 'px';
  wrap.style.left = '0';
  wrap.style.right = '0';

  for (let i = startIdx; i < endIdx; i++) {
    const s = _filtered[i];
    const div = document.createElement('div');
    div.className = 'stock-item' + (selected.has(s.code) ? ' checked' : '');
    div.style.height = ROW_H + 'px';
    div.innerHTML = `<input type="checkbox" ${selected.has(s.code)?'checked':''}>` +
      `<span class="code">${esc(s.code)}</span>` +
      `<span class="name">${esc(s.name)}</span>` +
      `<span class="market-tag">${getMarket(s.code).toUpperCase()}</span>`;
    div.onclick = (e) => { if(e.target.tagName!=='INPUT') div.querySelector('input').click(); };
    div.querySelector('input').onchange = () => toggleStock(s.code);
    wrap.appendChild(div);
  }
  space.appendChild(wrap);
}

// Scroll handler — update visible rows on scroll
document.getElementById('stockList').addEventListener('scroll', () => {
  requestAnimationFrame(renderVisible);
});

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function renderSelectedChips() {
  const el = document.getElementById('selectedList');
  document.getElementById('selCount').textContent = selected.size;
  document.getElementById('runBtn').disabled = selected.size === 0;
  if (selected.size === 0) {
    el.innerHTML = '<div class="empty-msg">No stocks selected.<br>Click checkboxes on the left to add.</div>';
    return;
  }
  let html = '';
  for (const code of selected) {
    const st = ALL_STOCKS.find(s => s.code === code);
    const name = st ? st.name : '';
    html += `<span class="selected-chip">${esc(code)} ${esc(name)} <span class="remove" onclick="toggleStock('${code}')">✕</span></span>`;
  }
  el.innerHTML = html;
}

// ── Toggle ────────────────────────────────────────────────────────────────
function toggleStock(code) {
  if (selected.has(code)) selected.delete(code); else selected.add(code);
  if (currentFilter === 'selected') refilter();
  renderVisible();
  renderSelectedChips();
}

function selectAllVisible() {
  _filtered.forEach(s => selected.add(s.code));
  renderVisible();
  renderSelectedChips();
}

function deselectAll() {
  selected.clear();
  if (currentFilter === 'selected') refilter();
  render();
}

// ── Tabs ──────────────────────────────────────────────────────────────────
document.getElementById('tabs').onclick = e => {
  if (e.target.tagName !== 'BUTTON') return;
  document.querySelectorAll('#tabs button').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  currentFilter = e.target.dataset.filter;
  refilter();
  render();
};

// ── Search (debounced) ───────────────────────────────────────────────────
let renderTimer = null;
document.getElementById('search').oninput = () => {
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => { refilter(); render(); }, 150);
};

// ── Run analysis ──────────────────────────────────────────────────────────
async function runAnalysis() {
  if (selected.size === 0) return;
  const codes = [...selected];
  const mode = document.getElementById('optMode').value;
  const fmt = document.getElementById('optFormat').value;

  const btn = document.getElementById('runBtn');
  const resDiv = document.getElementById('results');
  const log = document.getElementById('resultLog');
  const fill = document.getElementById('progressFill');

  btn.disabled = true;
  btn.textContent = '⏳ Running...';
  resDiv.style.display = 'block';
  log.innerHTML = '';
  fill.style.width = '0%';

  appendLog(`Starting analysis for ${codes.length} stock(s)...\n`, 'info');
  appendLog(`Mode: ${mode}  |  Format: ${fmt}\n`, 'info');
  appendLog('─'.repeat(50) + '\n', '');

  let done = 0;
  const total = codes.length;

  // Run analysis: single request with all codes
  try {
    const resp = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({codes, mode, format: fmt})
    });
    const data = await resp.json();
    if (data.success) {
      for (const r of (data.results || [])) {
        done++;
        fill.style.width = (done/total*100).toFixed(0) + '%';
        if (r.ok) {
          appendLog(`✓ ${r.code} ${r.name} — `, 'ok');
          appendLink(r.file, `/view/${encodeURIComponent(r.file)}`);
          appendLog('\n', '');
        } else {
          appendLog(`✗ ${r.code} — ${r.error}\n`, 'err');
        }
      }
      appendLog('\n' + '─'.repeat(50) + '\n', '');
      appendLog(`Done! ${data.results.filter(r=>r.ok).length}/${total} succeeded.\n`, 'info');
      if (data.compare_file) {
        appendLog('Comparison report: ', 'ok');
        appendLink(data.compare_file, `/view/${encodeURIComponent(data.compare_file)}`);
        appendLog('\n', '');
      }
      appendLog(`Output directory: ${data.out_dir}\n`, 'info');
      appendLog('\n', '');
      appendLink('📂 Open Reports Page →', '/reports');
      appendLog('\n', '');
    } else {
      appendLog(`Error: ${data.error}\n`, 'err');
    }
  } catch(e) {
    appendLog(`Network error: ${e.message}\n`, 'err');
  }

  fill.style.width = '100%';
  btn.disabled = false;
  btn.textContent = '▶ Run Analysis';
}

function appendLog(text, cls) {
  const log = document.getElementById('resultLog');
  const span = document.createElement('span');
  if (cls) span.className = cls;
  span.textContent = text;
  log.appendChild(span);
  log.scrollTop = log.scrollHeight;
}

function appendLink(text, href) {
  const log = document.getElementById('resultLog');
  const a = document.createElement('a');
  a.textContent = text;
  a.href = href;
  a.target = '_blank';
  log.appendChild(a);
  log.scrollTop = log.scrollHeight;
}

// ── Proxy Settings ───────────────────────────────────────────────────────
async function loadProxyInfo() {
  try {
    const resp = await fetch('/api/proxy', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action:'info'})
    });
    const data = await resp.json();
    if (data.success) {
      const p = data.proxy;
      const active = p.saved_url || p.env_https || p.default;
      document.getElementById('proxyStatus').textContent = 'Active: ' + active;
      document.getElementById('proxyUrl').value = p.saved_url || p.env_https || p.default;
    }
  } catch(e) {
    document.getElementById('proxyStatus').textContent = 'Error loading proxy info';
  }
}
loadProxyInfo();

async function saveProxy() {
  const url = document.getElementById('proxyUrl').value.trim();
  if (!url) return;
  const resp = await fetch('/api/proxy', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({action:'set', url})
  });
  const data = await resp.json();
  if (data.success) {
    document.getElementById('proxyStatus').textContent = 'Saved: ' + url;
  } else {
    document.getElementById('proxyStatus').textContent = 'Error: ' + data.error;
  }
}

async function testProxy() {
  const url = document.getElementById('proxyUrl').value.trim();
  const el = document.getElementById('proxyResult');
  el.style.display = 'block';
  el.innerHTML = 'Testing connectivity...';
  try {
    const resp = await fetch('/api/proxy', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action:'test', url: url || undefined})
    });
    const data = await resp.json();
    if (data.success) {
      const r = data.report;
      let html = 'Proxy: ' + r.proxy_url + '<br>';
      for (const t of r.results) {
        const cls = t.ok ? 'proxy-ok' : 'proxy-fail';
        const st = t.ok ? 'OK (' + t.status + ')' : 'FAIL (' + (t.error||'?') + ')';
        html += '<span class="' + cls + '">' + t.domain + ' → ' + st + '</span><br>';
      }
      el.innerHTML = html;
    } else {
      el.innerHTML = '<span class="proxy-fail">Error: ' + data.error + '</span>';
    }
  } catch(e) {
    el.innerHTML = '<span class="proxy-fail">Network error: ' + e.message + '</span>';
  }
}

// ── Sector Scan ──────────────────────────────────────────────────────────
async function runSectorScan() {
  const scanType = document.getElementById('scanType').value;
  const top = document.getElementById('scanTop').value;
  const btn = document.getElementById('scanBtn');
  const result = document.getElementById('scanResult');

  btn.disabled = true;
  btn.textContent = '⏳ Scanning...';
  result.style.display = 'block';
  result.innerHTML = '<div class="empty-msg">Loading sector data...</div>';

  try {
    const resp = await fetch('/api/sector-scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type: scanType, top: parseInt(top)})
    });
    const data = await resp.json();
    if (data.success) {
      renderScanResult(data.scan);
    } else {
      result.innerHTML = `<div class="empty-msg" style="color:var(--red)">Error: ${esc(data.error)}</div>`;
    }
  } catch(e) {
    result.innerHTML = `<div class="empty-msg" style="color:var(--red)">Network error: ${esc(e.message)}</div>`;
  }

  btn.disabled = false;
  btn.textContent = '📡 Scan Leading Groups';
}

function renderScanResult(scan) {
  const el = document.getElementById('scanResult');
  let html = '';

  if (scan.industry && scan.industry.length) {
    html += '<h3>🏭 Industry Boards — 行业板块</h3>';
    html += '<table><tr><th>#</th><th>Board</th><th>Chg%</th><th>↑</th><th>↓</th><th>Leader</th><th>L.Chg%</th><th></th></tr>';
    for (const b of scan.industry) {
      const cls = b.change_pct >= 0 ? 'pos' : 'neg';
      html += `<tr><td>${b.rank}</td><td><span class="board-link" onclick="drillBoard('${esc(b.name)}','industry')">${esc(b.name)}</span></td>`
        + `<td class="${cls}">${b.change_pct >= 0 ? '+' : ''}${b.change_pct.toFixed(2)}%</td>`
        + `<td>${b.rising}</td><td>${b.falling}</td>`
        + `<td>${esc(b.leader)}</td><td class="${b.leader_change >= 0 ? 'pos' : 'neg'}">${b.leader_change >= 0 ? '+' : ''}${b.leader_change.toFixed(2)}%</td>`
        + `<td></td></tr>`;
    }
    html += '</table>';
  }

  if (scan.concept && scan.concept.length) {
    html += '<h3>💡 Concept Boards — 概念板块</h3>';
    html += '<table><tr><th>#</th><th>Theme</th><th>Chg%</th><th>↑</th><th>↓</th><th>Leader</th><th>L.Chg%</th><th></th></tr>';
    for (const b of scan.concept) {
      const cls = b.change_pct >= 0 ? 'pos' : 'neg';
      html += `<tr><td>${b.rank}</td><td><span class="board-link" onclick="drillBoard('${esc(b.name)}','concept')">${esc(b.name)}</span></td>`
        + `<td class="${cls}">${b.change_pct >= 0 ? '+' : ''}${b.change_pct.toFixed(2)}%</td>`
        + `<td>${b.rising}</td><td>${b.falling}</td>`
        + `<td>${esc(b.leader)}</td><td class="${b.leader_change >= 0 ? 'pos' : 'neg'}">${b.leader_change >= 0 ? '+' : ''}${b.leader_change.toFixed(2)}%</td>`
        + `<td></td></tr>`;
    }
    html += '</table>';
  }

  if (scan.fund_flow_industry && scan.fund_flow_industry.length) {
    html += '<h3>💰 Fund Flow — 行业资金流</h3>';
    html += '<table><tr><th>#</th><th>Board</th><th>Chg%</th><th>Main Net</th><th>Net%</th></tr>';
    for (const f of scan.fund_flow_industry) {
      const cls = f.change_pct >= 0 ? 'pos' : 'neg';
      html += `<tr><td>${f.rank}</td><td>${esc(f.name)}</td>`
        + `<td class="${cls}">${f.change_pct >= 0 ? '+' : ''}${f.change_pct.toFixed(2)}%</td>`
        + `<td>${fmtYuan(f.main_net_inflow)}</td>`
        + `<td class="${f.main_net_pct >= 0 ? 'pos' : 'neg'}">${f.main_net_pct >= 0 ? '+' : ''}${f.main_net_pct.toFixed(2)}%</td></tr>`;
    }
    html += '</table>';
  }

  if (scan.fund_flow_concept && scan.fund_flow_concept.length) {
    html += '<h3>💰 Fund Flow — 概念资金流</h3>';
    html += '<table><tr><th>#</th><th>Theme</th><th>Chg%</th><th>Main Net</th><th>Net%</th></tr>';
    for (const f of scan.fund_flow_concept) {
      const cls = f.change_pct >= 0 ? 'pos' : 'neg';
      html += `<tr><td>${f.rank}</td><td>${esc(f.name)}</td>`
        + `<td class="${cls}">${f.change_pct >= 0 ? '+' : ''}${f.change_pct.toFixed(2)}%</td>`
        + `<td>${fmtYuan(f.main_net_inflow)}</td>`
        + `<td class="${f.main_net_pct >= 0 ? 'pos' : 'neg'}">${f.main_net_pct >= 0 ? '+' : ''}${f.main_net_pct.toFixed(2)}%</td></tr>`;
    }
    html += '</table>';
  }

  if (scan.leaders && scan.leaders.length) {
    html += '<h3>🏆 Leader Stocks — 龙头个股</h3>';
    for (const grp of scan.leaders) {
      const tag = grp.board_type === 'industry' ? '行业' : '概念';
      html += `<div style="margin:8px 0 4px;font-weight:600;color:var(--text)">[${tag}] ${esc(grp.board_name)} (${grp.board_change >= 0 ? '+' : ''}${grp.board_change.toFixed(2)}%)</div>`;
      html += '<table><tr><th>Code</th><th>Name</th><th>Price</th><th>Chg%</th><th>PE</th><th>PB</th><th></th></tr>';
      for (const s of grp.stocks) {
        const cls = s.change_pct >= 0 ? 'pos' : 'neg';
        html += `<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td>`
          + `<td>¥${s.price.toFixed(2)}</td>`
          + `<td class="${cls}">${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%</td>`
          + `<td>${s.pe.toFixed(1)}</td><td>${s.pb.toFixed(2)}</td>`
          + `<td><button class="add-btn" onclick="addStockFromScan('${esc(s.code)}')">+ Add</button></td></tr>`;
      }
      html += '</table>';
    }
  }

  if (!html) {
    html = '<div class="empty-msg">No data returned. Market may be closed.</div>';
  }

  el.innerHTML = html;
}

function fmtYuan(val) {
  const a = Math.abs(val);
  if (a >= 1e8) return (val / 1e8).toFixed(2) + '亿';
  if (a >= 1e4) return (val / 1e4).toFixed(1) + '万';
  return val.toFixed(0);
}

async function drillBoard(name, type) {
  const result = document.getElementById('scanResult');
  result.innerHTML = `<div class="empty-msg">Loading ${name} constituents...</div>`;
  try {
    const resp = await fetch('/api/sector-drill', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({board: name, type: type, top: 20})
    });
    const data = await resp.json();
    if (data.success) {
      let html = `<h3>📋 ${esc(name)} — Constituents</h3>`;
      html += '<table><tr><th>Code</th><th>Name</th><th>Price</th><th>Chg%</th><th>PE</th><th>PB</th><th></th></tr>';
      for (const s of data.stocks) {
        const cls = s.change_pct >= 0 ? 'pos' : 'neg';
        html += `<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td>`
          + `<td>¥${s.price.toFixed(2)}</td>`
          + `<td class="${cls}">${s.change_pct >= 0 ? '+' : ''}${s.change_pct.toFixed(2)}%</td>`
          + `<td>${s.pe.toFixed(1)}</td><td>${s.pb.toFixed(2)}</td>`
          + `<td><button class="add-btn" onclick="addStockFromScan('${esc(s.code)}')">+ Add</button></td></tr>`;
      }
      html += '</table>';
      html += `<div style="margin-top:8px"><button class="scan-btn" onclick="runSectorScan()" style="width:auto;padding:4px 16px;font-size:12px">← Back to Scan</button></div>`;
      result.innerHTML = html;
    } else {
      result.innerHTML = `<div class="empty-msg" style="color:var(--red)">Error: ${esc(data.error)}</div>`;
    }
  } catch(e) {
    result.innerHTML = `<div class="empty-msg" style="color:var(--red)">Network error: ${esc(e.message)}</div>`;
  }
}

function addStockFromScan(code) {
  const exists = ALL_STOCKS.find(s => s.code === code);
  if (!exists) {
    ALL_STOCKS.push({code: code, name: code});
  }
  if (!selected.has(code)) {
    selected.add(code);
    refilter();
    render();
  }
}
</script>
</body>
</html>"""


# ── HTTP handler ────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    """Minimal request handler — serves HTML + JSON API."""

    def log_message(self, fmt, *args):
        # quieter logging
        sys.stderr.write(f"[web] {args[0]}\n")

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content: str):
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filename: str):
        """Serve a raw file (png/md/txt) from the output directory."""
        # Sanitize: only allow basename, no path traversal
        safe_name = Path(filename).name
        fpath = Path(OUT_DIR).resolve() / safe_name
        if not fpath.is_file() or not fpath.resolve().is_relative_to(Path(OUT_DIR).resolve()):
            self.send_error(404)
            return
        ctype, _ = mimetypes.guess_type(safe_name)
        if ctype is None:
            ctype = "application/octet-stream"
        data = fpath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_report_view(self, filename: str):
        """Render a markdown/text report as an HTML page."""
        safe_name = Path(filename).name
        fpath = Path(OUT_DIR).resolve() / safe_name
        if not fpath.is_file() or not fpath.resolve().is_relative_to(Path(OUT_DIR).resolve()):
            self.send_error(404)
            return
        text = fpath.read_text(encoding="utf-8", errors="replace")
        if safe_name.endswith(".md"):
            body_html = _md_to_html(text)
        else:
            body_html = f"<pre>{_esc(text)}</pre>"
        # Extract title from frontmatter or first heading
        title = safe_name
        tm = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
        if tm:
            title = tm.group(1)
        self._html(_report_viewer_page(title, body_html, safe_name))

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/":
            self._html(_html_page())
        elif path == "/api/stocks":
            self._json(_load_stocks())
        elif path == "/api/reports":
            self._json(_list_report_files())
        elif path == "/reports":
            self._html(_reports_list_page(_list_report_files()))
        elif path.startswith("/view/"):
            self._serve_report_view(path[6:])
        elif path.startswith("/files/"):
            self._serve_file(path[7:])
        else:
            self.send_error(404)

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/analyze":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._json({"success": False, "error": "Invalid JSON"}, 400)
                return
            self._handle_analyze(body)
        elif path == "/api/sector-scan":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._json({"success": False, "error": "Invalid JSON"}, 400)
                return
            self._handle_sector_scan(body)
        elif path == "/api/sector-drill":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._json({"success": False, "error": "Invalid JSON"}, 400)
                return
            self._handle_sector_drill(body)
        elif path == "/api/proxy":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._json({"success": False, "error": "Invalid JSON"}, 400)
                return
            self._handle_proxy(body)
        else:
            self.send_error(404)

    def _handle_analyze(self, body: dict):
        codes = body.get("codes", [])
        mode = body.get("mode", "full")
        fmt = body.get("format", "markdown")

        # Validate inputs
        allowed_modes = {"structured", "full", "execution"}
        allowed_fmts = {"text", "markdown", "both"}
        if mode not in allowed_modes:
            mode = "full"
        if fmt not in allowed_fmts:
            fmt = "markdown"

        # Sanitize codes: only allow 6-digit numeric codes
        safe_codes = [c for c in codes if isinstance(c, str) and c.isdigit() and len(c) == 6]
        if not safe_codes:
            self._json({"success": False, "error": "No valid stock codes provided"})
            return

        out_dir = Path(OUT_DIR).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        results = []
        # Run each stock individually for progress granularity
        for code in safe_codes:
            name = _code_to_name(code)
            try:
                proc = subprocess.run(
                    [sys.executable, str(_SCRIPTS_DIR / "run_analysis.py"),
                     code, "--out-dir", str(out_dir), "--mode", mode, "--format", fmt],
                    capture_output=True, text=True, timeout=300, cwd=str(_SCRIPTS_DIR),
                )
                # Extract output file from stdout
                files = [line.split("→")[-1].strip()
                         for line in proc.stdout.splitlines()
                         if "→" in line]
                if proc.returncode == 0:
                    results.append({"ok": True, "code": code, "name": name,
                                    "file": files[-1] if files else "done"})
                else:
                    err_msg = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "Unknown error"
                    results.append({"ok": False, "code": code, "name": name, "error": err_msg})
            except subprocess.TimeoutExpired:
                results.append({"ok": False, "code": code, "name": name, "error": "Timeout (300s)"})
            except Exception as e:
                results.append({"ok": False, "code": code, "name": name, "error": str(e)})

        # If multiple stocks succeeded, also run comparison
        compare_file = None
        ok_codes = [r["code"] for r in results if r["ok"]]
        if len(ok_codes) >= 2:
            try:
                proc = subprocess.run(
                    [sys.executable, str(_SCRIPTS_DIR / "run_analysis.py"),
                     *ok_codes, "--out-dir", str(out_dir), "--mode", mode, "--format", fmt],
                    capture_output=True, text=True, timeout=600, cwd=str(_SCRIPTS_DIR),
                )
                if proc.returncode == 0:
                    files = [line.split("→")[-1].strip()
                             for line in proc.stdout.splitlines() if "→" in line]
                    compare_file = files[-1] if files else None
            except Exception:
                pass  # comparison is optional

        self._json({
            "success": True,
            "results": results,
            "compare_file": compare_file,
            "out_dir": str(out_dir),
        })

    def _handle_sector_scan(self, body: dict):
        scan_type = body.get("type", "all")
        top_n = body.get("top", 10)
        # Validate
        allowed_types = {"all", "industry", "concept", "fund-flow"}
        if scan_type not in allowed_types:
            scan_type = "all"
        if not isinstance(top_n, int) or top_n < 1 or top_n > 50:
            top_n = 10
        try:
            from sector_scan import full_scan
            scan = full_scan(top_boards=top_n, top_stocks=5, scan_type=scan_type)
            self._json({"success": True, "scan": scan})
        except Exception as e:
            self._json({"success": False, "error": str(e)})

    def _handle_sector_drill(self, body: dict):
        board_name = body.get("board", "")
        board_type = body.get("type", "industry")
        top_n = body.get("top", 20)
        if not board_name or board_type not in ("industry", "concept"):
            self._json({"success": False, "error": "Invalid board name or type"})
            return
        if not isinstance(top_n, int) or top_n < 1 or top_n > 100:
            top_n = 20
        try:
            from sector_scan import fetch_board_constituents
            stocks = fetch_board_constituents(board_name, board_type, top_n)
            self._json({"success": True, "stocks": stocks})
        except Exception as e:
            self._json({"success": False, "error": str(e)})

    def _handle_proxy(self, body: dict):
        action = body.get("action", "info")
        if action == "info":
            self._json({"success": True, "proxy": get_proxy_info()})
        elif action == "set":
            url = body.get("url", "").strip()
            if not url:
                self._json({"success": False, "error": "Proxy URL is required"})
                return
            configure_proxy(url, body.get("no_proxy"))
            self._json({"success": True, "proxy": get_proxy_info()})
        elif action == "test":
            url = body.get("url", "").strip() or None
            report = test_proxy(url)
            self._json({"success": True, "report": report})
        else:
            self._json({"success": False, "error": f"Unknown action: {action}"})


@lru_cache(maxsize=1)
def _name_map() -> dict[str, str]:
    """Build code→name dict once."""
    m = {}
    try:
        with open(_SYM_FILE, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                m[row["code"].strip()] = row["name"].strip()
    except Exception:
        pass
    return m


def _code_to_name(code: str) -> str:
    return _name_map().get(code, "")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Web-based stock selector for K-line analysis")
    parser.add_argument("--port", type=int, default=8686, help="Server port (default: 8686)")
    parser.add_argument("--out-dir", default=".", help="Directory for analysis output files")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    global OUT_DIR
    OUT_DIR = args.out_dir

    server = HTTPServer(("0.0.0.0", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"🚀 Stock Selector running at {url}")
    print(f"   Output dir: {os.path.abspath(args.out_dir)}")
    print(f"   Press Ctrl+C to stop\n")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[web] Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

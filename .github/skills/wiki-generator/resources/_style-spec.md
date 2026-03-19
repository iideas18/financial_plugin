# Wiki Style Specification

Single source of truth for CSS/JS patterns across all wiki pages. Reference this file
in subagent prompts instead of repeating CSS/JS rules inline.

> Replace `{{PROJECT_THEME_KEY}}` and `{{LANG}}` before use.

## Theme

- **Dark theme (default)**: `--bg:#0d1117; --surface:#161b22; --border:#30363d; --text:#c9d1d9; --text-muted:#8b949e; --accent:#58a6ff; --accent2:#3fb950; --accent3:#d29922; --accent4:#f85149; --heading:#f0f6fc; --code-bg:#1c2128`
- **Light theme** (`[data-theme="light"]`): `--bg:#ffffff; --surface:#f6f8fa; --border:#d0d7de; --text:#1f2328; --text-muted:#656d76; --accent:#0969da; --accent2:#1a7f37; --accent3:#9a6700; --accent4:#cf222e; --heading:#1f2328; --code-bg:#f6f8fa`

## localStorage Key

All pages use: `{{PROJECT_THEME_KEY}}-theme` (e.g., `keiko-theme`)

One key for the entire wiki — do NOT create per-module keys.

## CDN Dependencies

```html
<!-- Mermaid.js -->
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>mermaid.initialize({startOnLoad:false,theme:"default",flowchart:{useMaxWidth:true,htmlLabels:true,curve:"basis"}});</script>

<!-- Highlight.js 11.9.0 -->
<link id="hljs-theme" rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css">
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
```

## Critical Rules

1. `startOnLoad:false` — Mermaid must NOT auto-render before footer JS sets theme.
2. `pre code { background:none; color:inherit; padding:0 }` — never set `color` on `pre code` or hljs tokens break.
3. Code blocks use `class="language-{{LANG}}"` (e.g., `language-cpp`).
4. No hardcoded colors in Mermaid `style` lines — let theme engine handle colors.
5. Theme toggle uses `textContent` (NOT `innerHTML`) to restore mermaid source.
6. Breadcrumb separator: `›` (`&rsaquo;`) — never `>`, `→`, or `»`.
7. Every page needs a skip-link (`<a href="#main" class="skip-link">`) as first body element.
8. Theme toggle must have `aria-label="Toggle light/dark theme"`.
9. Breadcrumb `<nav>` elements must have `role="navigation" aria-label="Breadcrumb"`.
10. Main content wrapped in `<main id="main">`.
11. Every page includes `<meta name="wiki-generated" content="{{DATE}}">` and `<meta name="wiki-source" content="{{SOURCE_PATH}}">`.
12. Every page includes `@media print` block hiding toggle/skip-link and forcing light colors.
13. Every page includes `<meta name="wiki-source-rev" content="{{GIT_SHA}}">` for revision tracking.
14. L1/L2 pages include a `.copy-btn` on `<pre><code>` blocks (clipboard copy with "Copied!" feedback).
15. L0/L1/L2 pages include `.diagram-overlay` for click-to-zoom diagrams.
16. All pages include a `.back-to-top` button (visible after scrolling 400px).
17. L1/L2 pages auto-compute reading time (200 WPM) and display in `.hero`.
18. L2 pages auto-wrap tables with 8+ rows in `<details class="collapsible-table">`.
19. L1/L2 pages support `j`/`k` keyboard shortcuts to scroll between H2 sections.
20. Search page supports `/` keyboard shortcut to focus search input.
21. Focus pages include `<meta name="wiki-focus-parent" content="PARENT_PATH">` for parent tracking.
22. Focus pages use `.focus-label` badge, `.callout` boxes (`.warn`/`.danger`/`.success`), `.code-walk` with numbered steps.
23. After creating focus pages, run `link-focus-page.py` to insert link card in parent L2.
24. Do not minify generated HTML. Keep readable multi-line formatting so line-count checks measure content, not compression.
25. Parent extraction hubs should use `<h2 id="deep-dives">`, a `.hub-note` summary paragraph, and one shared `.card-grid.deep-dive-grid` block.
26. Do not mix a new extraction hub with the old long-form inline deep-dive sections for the same topic on the same L2 page.

## Deep Structure Defaults

- Focus pages: use an overview section, a 4-cell summary grid, a decision-point table, a mechanism walkthrough, a behavior diagram, a code walkthrough, edge cases, configuration, and related topics.
- Parent L2 extraction hub: keep only a short summary plus shared extracted-topic cards once a topic has been promoted.

```html
<h2 id="deep-dives">Deep-Dive Highlights</h2>
<p class="hub-note">Detailed mechanisms from this page have been extracted into dedicated focus pages. Keep only short summaries here and use the cards below for the full deep dive.</p>
<h4>Deep-Dive Pages</h4>
<div class="card-grid deep-dive-grid">
  <a class="card" href="topic_slug/index.html" title="Topic Name — Deep Dive">
    <h4>Topic Name <span class="focus-badge">Focus</span></h4>
    <p>Short description of the extracted topic.</p>
  </a>
</div>
```

## Theme Toggle Button

```html
<button class="theme-toggle" id="themeToggle" title="Toggle light/dark theme">&#9790;</button>
```

CSS: `.theme-toggle{position:fixed;top:1rem;right:1rem;z-index:1000;background:var(--surface);border:1px solid var(--border);border-radius:50%;width:40px;height:40px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.2rem;color:var(--text);transition:background .2s,border-color .2s;box-shadow:0 2px 8px rgba(0,0,0,.15)}`

## Footer JS (copy exactly)

```javascript
// Save mermaid source before first render
document.querySelectorAll('pre.mermaid').forEach(function(el){
  if(!el.getAttribute('data-source')) el.setAttribute('data-source',el.textContent);
});
(function(){
  var btn=document.getElementById('themeToggle');
  var hljsLink=document.getElementById('hljs-theme');
  var darkHL='https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css';
  var lightHL='https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github.min.css';
  function renderMermaid(t){
    var nodes=document.querySelectorAll('pre.mermaid');
    if(!nodes.length||!window.mermaid) return;
    nodes.forEach(function(el){
      var src=el.getAttribute('data-source');
      if(src){ el.removeAttribute('data-processed'); el.textContent=src; }
    });
    try{mermaid.initialize({startOnLoad:false,theme:(t==='light')?'default':'dark',flowchart:{useMaxWidth:true,htmlLabels:true,curve:'basis'}});mermaid.run();}catch(e){console.warn('mermaid re-render:',e);}
  }
  function applyTheme(t){
    document.documentElement.setAttribute('data-theme',t);
    hljsLink.href=(t==='light')?lightHL:darkHL;
    btn.textContent=(t==='light')?'☀':'☾';
    localStorage.setItem('{{PROJECT_THEME_KEY}}-theme',t);
    renderMermaid(t);
  }
  var saved=localStorage.getItem('{{PROJECT_THEME_KEY}}-theme')||(window.matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
  applyTheme(saved);
  btn.addEventListener('click',function(){applyTheme(document.documentElement.getAttribute('data-theme')==='light'?'dark':'light');});
})();
hljs.highlightAll();
```

## Light Theme CSS Block

```css
[data-theme="light"]{--bg:#ffffff;--surface:#f6f8fa;--border:#d0d7de;--text:#1f2328;--text-muted:#656d76;--accent:#0969da;--accent2:#1a7f37;--accent3:#9a6700;--accent4:#cf222e;--heading:#1f2328;--code-bg:#f6f8fa;--table-even:#f6f8fa;--table-odd:#ffffff}
[data-theme="light"] .hero{background:linear-gradient(135deg,#f0f4f8 0%,#ffffff 100%)}
[data-theme="light"] .badge{color:#fff}
[data-theme="light"] .card:hover{box-shadow:0 4px 12px rgba(0,0,0,.08)}
```

## Skip-Link CSS (Accessibility)

```css
.skip-link{position:absolute;top:-100%;left:1rem;background:var(--accent);color:#fff;padding:.5rem 1rem;border-radius:0 0 6px 6px;z-index:2000;font-size:.9rem;text-decoration:none;transition:top .2s}
.skip-link:focus{top:0}
```

## Print Stylesheet

```css
@media print{
  .theme-toggle,.skip-link,.copy-btn,.back-to-top,.diagram-overlay{display:none!important}
  body{max-width:100%;padding:1rem;color:#1f2328;background:#fff}
  :root{--bg:#fff;--surface:#f6f8fa;--border:#d0d7de;--text:#1f2328;--text-muted:#656d76;--accent:#0969da;--accent2:#1a7f37;--accent3:#9a6700;--accent4:#cf222e;--heading:#1f2328;--code-bg:#f6f8fa}
  .hero{background:#f0f4f8!important;border-color:#d0d7de}
  .card,.stat-box,.diagram-container{break-inside:avoid}
  a{color:#0969da}
  a[href]:after{content:" (" attr(href) ")"}
  .footer a[href]:after{content:none}
}
```

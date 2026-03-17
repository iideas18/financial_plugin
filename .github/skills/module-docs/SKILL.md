---
name: module-docs
description: "Generate self-contained HTML documentation with Mermaid diagrams for a source code module or directory. Use when asked to 'document this module', 'generate module docs', 'create HTML docs for this folder', 'document this component', or 'generate developer guide'. Produces a two-level set of HTML pages: one L1 overview with pipeline/architecture diagrams and clickable sub-module cards, plus one L2 deep-dive page per sub-module. Supports dark/light theme toggle, syntax highlighting, and Mermaid diagrams."
argument-hint: "Module path and optional language (e.g., 'src/core C++', 'backend/ Python')"
---

# Module Documentation Generator

Generate a two-level set of self-contained HTML pages for any source code module directory.

## When to Use

- Document a module, component, or directory in any codebase
- Create visual architecture docs with Mermaid diagrams
- Produce browsable HTML docs that work offline (file:// protocol)
- Onboard developers to a complex module

## Output Structure

```
docs/<module>_doc/
  index.html              ← L1: overview (architecture diagrams + sub-module cards)
  <submod1>/index.html    ← L2: deep-dive page
  <submod2>/index.html
  ...
```

**Rule**: Only L1 + L2. No L3. All sub-component details go directly on the L2 page.

---

## Procedure

### Phase 1 — Explore the Module

Before writing any HTML, gather deep understanding of the codebase.

1. **Identify sub-modules** — list the target directory to find sub-module folders:
   ```
   ls <module>/
   ```

2. **Gauge scope** — count source files and lines:
   ```
   find <module>/ -name '*.h' -o -name '*.cc' -o -name '*.cpp' -o -name '*.py' -o -name '*.ts' -o -name '*.java' | head -80
   wc -l <module>/**/*.{h,cc,cpp}  # adjust extensions for the language
   ```

3. **Deep research** — use a read-only subagent (Explore agent, thoroughness: thorough) to read key files and produce a structured report covering:
   - Purpose and role of the module
   - Key classes, structs, enums, functions
   - Data flow and interactions between sub-modules
   - Configuration, knobs, stats

### Phase 2 — Create L1 Overview Page

Create `docs/<module>_doc/index.html` using the [L1 template](./resources/l1-template.html).

Required sections:
- **Hero banner**: module name, subtitle, 2–3 sentence summary
- **Stat row**: sub-module count, key metrics (pipeline stages, threads, language, etc.)
- **Badges**: key traits as colored pills
- **Architecture Mermaid diagram** (`flowchart LR`) showing sub-module connections
- **Data-flow Mermaid diagram** (`flowchart TD`) showing request/response paths
- **Card grid**: one clickable `<a class="card">` per sub-module linking to `<submod>/index.html`

### Phase 3 — Create L2 Pages (batch 4–5 at a time)

Create each `docs/<module>_doc/<submod>/index.html` using the [L2 template](./resources/l2-template.html).

Required sections:
- **Breadcrumb**: `<module> › <submod>`
- **Hero**: sub-module name + purpose
- **Stat row**: classes/functions, files, lines, key metric
- **Table of Contents** (2-column `.toc`)
- **Architecture Mermaid diagram** (class diagram or flowchart)
- **Tables** for: key classes/functions, data structures/enums, interactions, configuration
- **Code examples** in `<pre><code class="language-{LANG}">` blocks
- **Footer** link back to L1

### Phase 4 — Verify

Run these checks after generating all pages:

```bash
# All pages have theme toggle
grep -rlc 'themeToggle' docs/<module>_doc/

# All pages have syntax highlighting
grep -rlc 'hljs' docs/<module>_doc/

# Code blocks have language class
grep -rlc 'language-' docs/<module>_doc/

# No bad patterns
grep -rl 'startOnLoad:true' docs/<module>_doc/        # should be 0
grep -rl 'el\.innerHTML=src' docs/<module>_doc/        # should be 0
grep -Pl 'pre code\s*\{[^}]*color:' docs/<module>_doc/ # should be 0
```

---

## Batch Updates

When applying fixes or theme support across all pages at once, use the [batch update script](./scripts/batch_update.py) as a starting point rather than editing files individually. Copy it into the docs folder, customize the transformations, run it, then delete it.

---

## Key Rules

1. **Self-contained HTML** — every page embeds all CSS inline in `<style>`. No external CSS links. Pages must work when opened directly via `file://`.

2. **`pre code` must NOT set `color`** — otherwise highlight.js token colors are overridden. Use `pre code{background:none;padding:0}` only.

3. **Code blocks use `class="language-{LANG}"`** — set the appropriate language class for highlight.js (e.g., `language-cpp`, `language-python`, `language-typescript`).

4. **localStorage key pattern**: `<module>-theme` (e.g., `coho-theme`, `backend-theme`).

5. **Mermaid re-render on theme change** — save original source in `data-source` attr before first render; on toggle, restore via `el.textContent` (NOT `innerHTML` — that corrupts angle brackets like `<<abstract>>`), re-init with new theme, call `mermaid.run()`.

6. **No hardcoded colors in Mermaid `style` lines** — do NOT add `style NodeName fill:#0d1117,...` in diagrams. Let Mermaid's theme engine handle colors (`'dark'` / `'default'`). Hardcoded fills break in the opposite theme.

7. **`startOnLoad:false`** in `<head>` — Mermaid must NOT auto-render before the footer JS determines the correct theme.

8. **Research before writing** — use the Explore subagent with `thoroughness: thorough` to read source files before writing content. Documentation quality depends on this step.

## CSS Design Tokens

| Token | Dark | Light |
|-------|------|-------|
| `--bg` | `#0d1117` | `#ffffff` |
| `--surface` | `#161b22` | `#f6f8fa` |
| `--border` | `#30363d` | `#d0d7de` |
| `--text` | `#c9d1d9` | `#1f2328` |
| `--text-muted` | `#8b949e` | `#656d76` |
| `--accent` | `#58a6ff` | `#0969da` |
| `--accent2` | `#3fb950` | `#1a7f37` |
| `--accent3` | `#d29922` | `#9a6700` |
| `--accent4` | `#f85149` | `#cf222e` |
| `--heading` | `#f0f6fc` | `#1f2328` |
| `--code-bg` | `#1c2128` | `#f6f8fa` |

## CDN Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| Mermaid.js | 10.x | Diagrams (flowchart, class, sequence) |
| Highlight.js | 11.9.0 | Code syntax highlighting |

## Component CSS Classes

| Class | Usage |
|-------|-------|
| `.hero` | Full-width banner with subtitle + description |
| `.stat-row > .stat-box` | Metric cards (`.num` + `.label`) |
| `.badge.{blue,green,yellow,red}` | Colored tag pills |
| `.diagram-container` | Theme-adaptive wrapper for `<pre class="mermaid">` |
| `.card-grid > .card` | Clickable sub-module cards (L1) or info cards (L2) |
| `.toc` | Two-column table of contents |
| `.breadcrumb` | Navigation breadcrumbs |
| `.footer` | Centered footer with back-link |
| `.theme-toggle` | Fixed floating dark/light toggle button |

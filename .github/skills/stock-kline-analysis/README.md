# Financial Plugin

A VS Code skill workspace for stock market analysis, sector scanning, and agent-driven trading workflows.

## Quick Start

```bash
# Install dependencies
pip install akshare matplotlib pandas numpy

# Launch the web UI
python .github/skills/stock-kline-analysis/scripts/web_selector.py --port 8686

# CLI analysis
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 000063 --format markdown

# Sector scan
python .github/skills/stock-kline-analysis/scripts/sector_scan.py --type all --top 10
```

Open `http://localhost:8686` to access the full web interface.

## Features

### Web UI (web_selector.py)

- **Stock Selector** — searchable, filterable list of 4,500+ A-share stocks with virtual scrolling
- **Batch Analysis** — select multiple stocks and run analysis in one click
- **Report Viewer** — browse and read rendered markdown reports in-browser
- **Sector Scanner** — scan industry boards, concept boards, and fund flows for leading groups
- **Drill-down** — click any board to see its top constituent stocks, then add them to analysis
- **Proxy Settings** — configure and test corporate proxy from the UI

### Stock Analysis (run_analysis.py)

- Auto-detect market from stock code (A-share SH/SZ, HK, US)
- Fetch daily/weekly/monthly K-line data via AkShare
- Compute MA5/MA20/MA60, Bollinger Bands, MACD, RSI-14, ATR-14
- Generate candlestick charts with indicator overlays
- Structured, full, or execution-oriented report modes
- Multi-symbol relative strength comparison
- Markdown and text output with YAML frontmatter

### Sector Scanner (sector_scan.py)

- Industry board ranking by daily change
- Concept/theme board ranking
- Sector fund flow (main net inflow) ranking
- Board constituent drill-down with leader stock identification
- 30-minute cache, 3× retry with backoff
- CLI and API modes

### Livermore Trading Agent

- Jesse Livermore–style trading analysis persona
- Top-down workflow: leading groups → leader stocks → pivotal points
- Structured output: trend, timing, risk, position sizing
- Invoked via Copilot Chat with the `@livermore` agent

### Proxy Configuration (proxy_config.py)

- Centralized proxy management for corporate networks
- Persistent settings saved to `scripts/data/proxy.json`
- CLI and web UI configuration
- Connectivity testing against East Money API domains

## Skills

| Skill | Path | Purpose |
|---|---|---|
| stock-kline-analysis | `.github/skills/stock-kline-analysis/` | K-line fetch, indicators, charts, analysis reports |
| transfer-skill-to-windows | `.github/skills/transfer-skill-to-windows/` | Adapt skills for Windows/PowerShell |
| email-rewrite | `.github/skills/email-rewrite/` | Polish and improve email drafts |
| module-docs | `.github/skills/module-docs/` | Generate HTML documentation with Mermaid diagrams |
| repo-docs-generator | `.github/skills/repo-docs-generator/` | Generate project overview docs |
| resume-optimize | `.github/skills/resume-optimize/` | Resume scoring and optimization |
| xiaohongshu-skills | `.github/skills/xiaohongshu-skills/` | 小红书 automation |

## Agents

| Agent | Path | Purpose |
|---|---|---|
| livermore | `.github/agents/livermore.agent.md` | Jesse Livermore trading analysis |

## Repository Layout

```text
.
├── .github/
│   ├── agents/
│   │   └── livermore.agent.md
│   └── skills/
│       ├── stock-kline-analysis/
│       │   ├── SKILL.md
│       │   └── scripts/
│       │       ├── web_selector.py      # Web UI server
│       │       ├── run_analysis.py      # CLI analysis orchestrator
│       │       ├── sector_scan.py       # Sector/board scanner
│       │       ├── fetch_kline.py       # K-line data fetching + cache
│       │       ├── chart.py             # Candlestick chart rendering
│       │       ├── indicators.py        # Technical indicator calculations
│       │       ├── valuation.py         # Fundamental data (PE/PB)
│       │       ├── events.py            # Market events overlay
│       │       ├── proxy_config.py      # Proxy configuration
│       │       └── data/
│       │           ├── a_share_symbols.csv  # 4,500+ stock codes & names
│       │           └── proxy.json           # Saved proxy settings
│       ├── transfer-skill-to-windows/
│       └── ...other skills
└── README.md
```

## Requirements

- Python 3.10+
- akshare, matplotlib, pandas, numpy
- VS Code with GitHub Copilot Chat (for skill/agent integration)

## Proxy Notes

Behind a corporate proxy, configure it before first use:

```bash
# CLI
python .github/skills/stock-kline-analysis/scripts/proxy_config.py --set http://your-proxy:port --test

# Or use the Web UI → Proxy Settings section
```
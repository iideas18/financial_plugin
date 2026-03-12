# financial_plugin

A collection of AI agent skills for financial analysis. Currently includes **stock-kline-analysis** — auto-detect market, fetch K-line data, compute technical indicators, generate charts, and deliver structured analysis with valuation context and event-aware risk notes.

---

## Skills

| Skill | Description |
|---|---|
| [`stock-kline-analysis`](stock-kline-analysis/SKILL.md) | K-line chart + MA/Bollinger/MACD/RSI/ATR analysis for A-share, HK, and US stocks |

---

## How to Add This as a Skill

### GitHub Copilot (VS Code)

1. **Copy the skill folder** into your project's `.github/skills/` directory (create it if it doesn't exist):

   ```bash
   # From your project root
   mkdir -p .github/skills
   cp -r /path/to/stock-kline-analysis .github/skills/
   ```

   Or clone directly:

   ```bash
   git clone https://github.com/iideas18/financial_plugin.git /tmp/financial_plugin
   cp -r /tmp/financial_plugin/stock-kline-analysis .github/skills/
   ```

2. **Reference the skill** in your Copilot instructions file (`.github/copilot-instructions.md`):

   ```markdown
   ## Skills
   
   Use the skill at `.github/skills/stock-kline-analysis/SKILL.md` when the user asks about
   stock analysis, K-line charts, or technical indicators.
   ```

3. **Use it** — in Copilot Chat (`Ctrl+Shift+I`), just ask naturally:

   ```
   Analyze 600519
   K-line chart for AAPL
   Compare 000001 and 600036
   ```

---

### Claude Code (Anthropic Claude CLI)

1. **Copy the skill** to your project's `.claude/skills/` directory:

   ```bash
   mkdir -p .claude/skills
   cp -r /path/to/stock-kline-analysis .claude/skills/
   ```

2. **Register the skill** in your project's `CLAUDE.md` (create at project root if absent):

   ```markdown
   ## Skills
   
   <skill>
   <name>stock-kline-analysis</name>
   <description>
     Given a stock name or code, auto-detect its market, fetch 6-month daily K-line,
     plot candlestick + MA/Bollinger/MACD/RSI/ATR with multi-timeframe confirmation,
     and deliver structured analysis with trend, momentum, valuation context,
     portfolio-relative strength, and event-aware risk notes.
   </description>
   <file>.claude/skills/stock-kline-analysis/SKILL.md</file>
   </skill>
   ```

3. **Use it** — in any Claude Code session:

   ```
   Analyze 贵州茅台
   How is TSLA doing technically?
   Compare 600519 and 000858 by relative strength
   ```

---

### OpenClaw

1. **Place the skill folder** under your OpenClaw agent directory (typically `.agents/skills/`):

   ```bash
   mkdir -p .agents/skills
   cp -r /path/to/stock-kline-analysis .agents/skills/
   ```

2. **Register the skill** by adding an entry to your agent configuration (`.agents/config.yaml` or equivalent):

   ```yaml
   skills:
     - name: stock-kline-analysis
       description: >
         Given a stock name or code, auto-detect its market, fetch 6-month daily K-line,
         plot candlestick + MA/Bollinger/MACD/RSI/ATR with multi-timeframe confirmation,
         and deliver structured analysis with trend, momentum, valuation context,
         portfolio-relative strength, and event-aware risk notes.
       file: .agents/skills/stock-kline-analysis/SKILL.md
   ```

3. **Use it** — invoke the agent as usual; it will auto-route stock analysis requests to this skill.

---

## Quick Start (standalone scripts)

Install dependencies:

```bash
pip install akshare pandas matplotlib mplfinance
```

Run analysis directly:

```bash
python stock-kline-analysis/scripts/run_analysis.py 600519
python stock-kline-analysis/scripts/run_analysis.py AAPL --out-dir /tmp/reports
python stock-kline-analysis/scripts/run_analysis.py 贵州茅台
```

---

## Repository

```
stock-kline-analysis/
├── SKILL.md          # Skill definition (instructions for AI agents)
└── scripts/
    ├── run_analysis.py   # CLI orchestrator
    ├── fetch_kline.py    # Multi-timeframe K-line fetch
    ├── indicators.py     # MA / Bollinger / MACD / RSI / ATR
    ├── chart.py          # 4-panel matplotlib chart
    ├── valuation.py      # EPS / PE / PB / ROE
    └── events.py         # Macro event calendar overlay
```

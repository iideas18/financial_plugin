# stock-kline-analysis

Stock K-line analysis skill for A-share, HK, and US symbols.

It resolves a stock name or code, fetches recent K-line data, computes technical indicators, renders a chart, and produces either a structured analysis report or an execution-oriented trade plan. It also supports multi-symbol relative-strength comparison with leader / laggard plans, unified priority guidance, and indicative portfolio weights.

## What It Does

- Resolves stock codes and Chinese stock names automatically
- Fetches daily, weekly, and monthly OHLCV data
- Computes MA5 / MA20 / MA60, Bollinger Bands, MACD, RSI-14, and ATR-14
- Generates a matplotlib K-line chart
- Adds valuation context for A-shares when the data source is available
- Adds macro-event overlay with fallback calendar support
- Produces execution-style outputs such as entry zones, stop zones, watchlists, and open-vs-close bias
- Compares multiple symbols by relative strength
- Produces leader / laggard execution plans
- Produces 3+ symbol portfolio guidance with main-position, watch-only, and exclude buckets

## Files

- [SKILL.md](g:/repo/skill_to_windows/.github/skills/stock-kline-analysis/SKILL.md): skill instructions and behavior contract
- [scripts/run_analysis.py](g:/repo/skill_to_windows/.github/skills/stock-kline-analysis/scripts/run_analysis.py): main CLI entrypoint
- [scripts/fetch_kline.py](g:/repo/skill_to_windows/.github/skills/stock-kline-analysis/scripts/fetch_kline.py): K-line fetch + local cache fallback
- [scripts/indicators.py](g:/repo/skill_to_windows/.github/skills/stock-kline-analysis/scripts/indicators.py): technical indicators
- [scripts/chart.py](g:/repo/skill_to_windows/.github/skills/stock-kline-analysis/scripts/chart.py): chart rendering
- [scripts/valuation.py](g:/repo/skill_to_windows/.github/skills/stock-kline-analysis/scripts/valuation.py): valuation fetch and PE/PB derivation
- [scripts/events.py](g:/repo/skill_to_windows/.github/skills/stock-kline-analysis/scripts/events.py): event overlay

## Requirements

- Python environment with `akshare`, `pandas`, `numpy`, and `matplotlib`
- Network access for live market and valuation/event fetches
- Windows is supported; chart rendering includes Chinese font fallbacks

## Basic Usage

Run a single-symbol structured report:

```bash
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 600519
python .github/skills/stock-kline-analysis/scripts/run_analysis.py AAPL
```

Write output files to a specific folder:

```bash
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 --out-dir test/stock-kline-analysis-output
```

## Output Modes

`run_analysis.py` supports three output modes:

- `structured`: classic structured analysis report
- `full`: structured report plus execution plan, watchlist, timing bias, and comparison extras
- `execution`: execution-focused version for trading-style prompts

Examples:

```bash
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 --mode full
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 --mode execution
```

## Multi-Symbol Comparison

Pass two or more symbols or names to switch into relative-strength mode automatically.

```bash
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 五粮液 --mode full
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 600519 600809 000858 000568 --mode execution
```

Comparison output includes:

- Relative-strength ranking table
- `Leader` and `Laggard`
- Leader and laggard trade plans
- Unified priority buckets: `右侧优先`, `只配观察`, `应回避`
- Portfolio suggestion section for 3+ symbols
- Indicative weight guidance when the user did not provide a custom risk budget

Default portfolio framework for 3+ symbols:

- Main-position candidates: 70% total
- Watch-only bucket: 30% total
- Excluded names: 0%

Weights are then split within each bucket by relative rank strength.

## Cache Behavior

The fetch layer stores successful K-line responses in a local cache under the skill's `.cache` directory.

Behavior:

- Live fetch succeeds: cache is updated
- Live fetch fails: the latest cached frame is reused if available
- Reports surface freshness metadata instead of hiding cache usage

Freshness sections may include:

- data source: live or cache fallback
- cache file name
- cache timestamp
- last bar date
- lag versus current date

This makes multi-symbol comparison more resilient when one symbol hits a transient upstream failure.

## Output Sections

Depending on mode and prompt intent, reports may include:

- `Symbol Summary`
- `K-Line Snapshot`
- `Technical View`
- `Valuation`
- `Event Overlay`
- `Risk & Watchpoints`
- `Trading Plan — 交易执行版`
- `Watchlist — 三段式盯盘清单`
- `Timing Bias — 早盘 vs 尾盘`
- `Relative Strength`
- `Priority Guidance — 统一优先级建议`
- `Portfolio Suggestion — 组合建议版`
- `Data Freshness` or `Cache Freshness`

## Notes

- Chinese name resolution uses the A-share symbol list first and avoids misclassifying Chinese names as US tickers.
- Valuation fetches degrade gracefully when the remote source is slow or unavailable.
- Relative-strength output is ranking-based and not a full portfolio optimizer.
- Nothing in the output should be interpreted as guaranteed direction or investment advice.

## Example Prompts

- Analyze 贵州茅台 and show Bollinger Bands, MACD, RSI, and ATR stop-loss.
- Compress 贵州茅台 into a trading-style execution plan with entry, stop, and watch levels.
- Compare 贵州茅台, 五粮液, and 泸州老窖 by relative strength.
- Give me a portfolio suggestion with main-position candidates, watch-only names, exclusions, and indicative weights.
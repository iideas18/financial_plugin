---
name: stock-kline-analysis
description: Given a stock name or code, auto-detect its market, fetch 6-month daily K-line, plot candlestick + MA/Bollinger/MACD/RSI/ATR with multi-timeframe confirmation, and deliver structured analysis with trend, momentum, valuation context, portfolio-relative strength, and event-aware risk notes.
---

# Stock K-Line Analysis Skill

Use this skill when the user gives a stock name or code and wants K-line output and/or analysis, e.g.:
- "Analyze 600519"
- "K-line and trend for 贵州茅台"
- "How is AAPL doing?"
- "Compare 000001 and 600036 by relative strength"

## Defaults (baked-in)

| Parameter | Default |
|---|---|
| Market | Auto-detect; only ask if unresolvable or genuinely ambiguous |
| K-line period | Daily (primary) + Weekly & Monthly for multi-timeframe |
| Time range | Last 6 months (today − 182 days) for daily; auto-extend for weekly/monthly |
| Price adjust | `qfq` for A-share; none for HK/US |
| Indicators | MA5/MA20/MA60, Bollinger Bands (20,2), MACD (12/26/9), RSI-14, ATR-14 |
| Language | Bilingual: Chinese label + English explanation |
| Output style | `structured` by default; support `full` and `execution` when user asks for交易视角/执行版/盯盘清单 |

User overrides these defaults at any time.

## Market Auto-Detection Rules

| Code pattern | Inferred market |
|---|---|
| 6-digit starting with 6 | A-share Shanghai |
| 6-digit starting with 0 or 3 | A-share Shenzhen |
| 5-digit starting with 0 | HK (prefix `0`) |
| 4–5 chars, letters | US (NYSE/NASDAQ) |
| Name only | Search A-share first, then HK; disambiguate if needed |

If detection confidence is low, list top-2 candidates and ask once.

Important implementation note:
- Treat **US ticker detection as ASCII-only letters**. Do not use plain `.isalpha()` because Chinese names also return true and will be misclassified as US symbols.

## AkShare API Reference

| Market | AkShare function |
|---|---|
| A-share daily | `ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date, adjust="qfq")` |
| A-share real-time | `ak.stock_zh_a_spot_em()` (network may fail — wrap in try/except) |
| HK daily | `ak.stock_hk_daily(symbol, adjust="qfq")` |
| US daily | `ak.stock_us_daily(symbol, adjust="qfq")` |
| A-share symbol list | `ak.stock_info_a_code_name()` |
| Financial indicators | `ak.stock_financial_analysis_indicator(symbol, start_year)` — EPS, ROE, margins (use this; `stock_a_lg_indicator` does NOT exist) |
| Latest earnings summary | `ak.stock_yjbb_em(date="YYYYMMDD")` — EPS, revenue, net profit YoY, industry |
| Industry PE | `ak.stock_industry_pe_ratio_cninfo(symbol)` |
| Macro calendar | `ak.news_economic_baidu()` — date column is `datetime.date` objects; data may be stale (up to ~2 months behind current date) |

## Scripts

All implementation code lives in `scripts/` next to this file. You can run a full analysis end-to-end with:

```bash
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 000063
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台
python .github/skills/stock-kline-analysis/scripts/run_analysis.py AAPL --out-dir /tmp/reports
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 --mode full
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 --mode execution
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 五粮液 --mode full
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 --format text   # plain text only
python .github/skills/stock-kline-analysis/scripts/run_analysis.py 贵州茅台 --format both   # text + markdown
```

Output format options (`--format`):
- `markdown` (default): saves a `.md` file with YAML frontmatter, timestamp in filename (`{code}_analysis_YYYYMMDD_HHMM.md`), and embedded chart image link. Also saves `.txt`.
- `text`: saves `.txt` only (legacy behavior).
- `both`: saves both `.txt` and `.md`.

Markdown files include:
- YAML frontmatter (`title`, `date`, `generator`)
- Timestamp-stamped filename for version tracking
- Properly formatted tables, bullet lists, and bold/italic markers
- Relative image links to chart PNGs
- For multi-stock comparisons: `{code1}_vs_{code2}_relative_strength_YYYYMMDD_HHMM.md`

| Script | Purpose |
|---|---|
| `scripts/run_analysis.py` | CLI orchestrator — runs all steps end-to-end |
| `scripts/fetch_kline.py` | Step 2 — multi-timeframe K-line fetch with retry/fallback |
| `scripts/indicators.py` | Step 3 — compute MA/BB/MACD/RSI/ATR for all timeframes |
| `scripts/chart.py` | Step 4 — 4-panel matplotlib chart (K线+BB \| Vol \| MACD \| RSI-14) |
| `scripts/valuation.py` | Step 5 — fetch EPS/revenue/ratios and compute PE/PB |
| `scripts/events.py` | Step 7 — macro events with hardcoded fallback calendar |

Each script has a `__main__` smoke-test (e.g. `python fetch_kline.py 000063`).

`run_analysis.py` supports:
- `--mode structured`: original structured report only
- `--mode full`: structured report + trading plan + watchlist + open-vs-close bias
- `--mode execution`: same execution-oriented sections when the user explicitly wants a交易执行版
- Passing multiple symbols/names switches into relative-strength comparison mode automatically

---

## Workflow

### Step 1 — Resolve Identifier

1. Apply market auto-detection rules to the raw input.
2. If code is numeric and 6-digit, run `ak.stock_info_a_code_name()` to confirm name.
3. If name is given, filter symbol list for closest match.
4. If ambiguous (>1 high-confidence match), show max 3 options and ask.
5. If unresolvable, report clearly and stop.

If the raw input is Chinese text, it must go through the A-share/HK name lookup path before any US-ticker branch.

Completion check: one confirmed `{code, name, market}` tuple before fetching any data.

---

### Step 2 — Fetch K-Line Data

See **`scripts/fetch_kline.py`** — `fetch_all_timeframes(code, adjust="qfq")` returns `(df_daily, df_weekly, df_monthly)`, all normalized.

Key implementation notes (do NOT get wrong):
- `stock_zh_a_hist` returns **12 Chinese-named columns** — always use explicit `rename(col_map)`, never positional assignment.
- Windows: daily = last 182 days, weekly = last 365 days, monthly = last 3 years.
- Persist successful fetches to a **local cache** and reuse the latest cached frame if a later network call fails. This is especially important for multi-symbol comparisons where one transient failure should not kill the whole report.
- Attach cache metadata to fetched frames so the final output can say whether the data came from `实时抓取` or `本地缓存回退`, when the cache file was written, and what the latest bar date is.

```python
from scripts.fetch_kline import fetch_all_timeframes
df_daily, df_weekly, df_monthly = fetch_all_timeframes(code)
```

Fallback logic:
- On network error, retry up to 3 times with short backoff.
- If retries fail but a local cached frame exists for the same symbol/timeframe, use the cache and clearly note it.
- Surface cache freshness in the report; do not silently hide that cached data was used.
- If daily fetch is empty: report (suspended / delisted / wrong symbol / holiday) and stop.
- Weekly/monthly failures: skip that timeframe and note it in output.

Completion check: `len(df_daily) > 20` and all OHLCV columns present and non-null.

---

### Step 3 — Compute Indicators

See **`scripts/indicators.py`** — `add_indicators(df)` and `add_tf_indicators(df_weekly, df_monthly)`.

Critical notes:
- `bb_width` = `(upper − lower) / mid * 100` — result is a **percentage** (e.g. 12.7, not 0.127).
- RSI must use a standalone helper; do **not** chain `.diff()` twice on the same series.
- Support/resistance stored in `df.attrs["support"]` / `df.attrs["resistance"]`.

```python
from scripts.indicators import add_indicators, add_tf_indicators
df_daily = add_indicators(df_daily)
df_weekly, df_monthly = add_tf_indicators(df_weekly, df_monthly)
```

If fewer than 60 bars exist on daily, use all available and note the limitation. Bollinger Bands require minimum 20 bars.

---

### Step 4 — Build K-Line Chart

**Primary path — matplotlib** (4-panel: K线+布林带 | 成交量 | MACD | RSI-14):

See **`scripts/chart.py`** — `plot_kline(df, code, name, out_path, market_label, dpi)` returns the saved path.

> `mplfinance` is **NOT installed** in the base environment. `chart.py` calls `matplotlib.use("Agg")` at module level — always import before pyplot.
> On Windows, configure CJK-capable font fallbacks (`Microsoft YaHei`, `SimHei`, etc.) so Chinese titles do not render as missing glyphs.

```python
from scripts.chart import plot_kline
chart_path = plot_kline(df_daily, code=code, name=name, market_label="A股",
                        out_path=f"{code}_kline.png")
```

Fallback (text table — only if matplotlib is also unavailable), latest 20 bars:
```
date        close   MA20    BB_up   BB_low  RSI14   ATR%
2026-02-10  15.38   14.90   16.20   13.60   58.3    1.4%
...
```

---

### Step 5 — Valuation Context

See **`scripts/valuation.py`** — `fetch_valuation(code)` and `compute_pe_pb(result, last_close)`.

> `ak.stock_a_lg_indicator` and `ak.stock_a_indicator_lg` **do not exist** — use `stock_yjbb_em` + `stock_financial_analysis_indicator` instead (both implemented in `valuation.py`).
> `stock_yjbb_em(date=...)` may not have the symbol for the newest quarter yet. Try recent quarter-ends in newest-first order until the symbol is found, instead of failing after one date.

```python
from scripts.valuation import fetch_valuation, compute_pe_pb
val = fetch_valuation(code)
val = compute_pe_pb(val, last_close=float(df_daily["close"].iloc[-1]))
# val keys: eps, revenue, revenue_yoy, net_profit, net_profit_yoy,
#           book_value_per_share, roe, gross_margin, industry,
#           report_date, fin_df, pe_ttm, pb
```

For HK/US: skip valuation section or note it as unavailable.

Report:
- Current PE (TTM, computed from EPS), PB.
- ROE and net profit margin.
- Revenue/profit YoY growth from latest report.
- Industry classification.
- Note: historical PE percentile not available without `stock_a_lg_indicator`; skip that sub-bullet and state the reason.

---

### Step 6 — Portfolio / Relative Strength Mode

Activated when user provides multiple symbols (e.g. "compare 600519 and 000858").

1. Fetch 6-month daily data for all symbols (same window as default).
2. Compute normalized 6-month return (base=100 on start date).
3. Compute 20-day rolling volatility and ATR% for each symbol.
4. Rank by: return, Sharpe-proxy (return/vol), RSI, and ATR% (lower = more stable).
5. Produce a comparison table and identify the relative leader.
6. In `full` / `execution` mode, append **leader / laggard execution plans** derived from each symbol's own support, resistance, MA20 and ATR.
7. If the comparison set has **3 or more symbols**, append a **unified priority guide** with three buckets: `右侧优先`, `只配观察`, `应回避`.
8. If the comparison set has **3 or more symbols**, append a **portfolio suggestion section** with `主仓候选`, `观察仓`, `排除名单`, and `主仓首选`.
9. The portfolio suggestion section should include **indicative weight guidance** so the user can distinguish higher-weight main positions from lower-weight observation slots.

Single-symbol mode: compare to its own industry index if identifiable.

Comparison-mode output requirements:
- Always identify one `Leader` and one `Laggard` from the computed composite rank.
- The leader plan should emphasize right-side confirmation / breakout following when its structure supports it.
- The laggard plan should emphasize rebound-trial-only unless it reclaims its confirmation line.
- Do not reuse one symbol's levels for another; each plan must be computed from that symbol's own dataset.
- For 3+ symbols, explicitly list which symbols belong to `右侧优先`, which are `只配观察`, and which are `应回避`.
- If even the leader has negative 6M return, state that `右侧优先` is only a **relative** preference, not a confirmed trend endorsement.
- The portfolio suggestion is a ranking-based allocation hint, not a sizing engine; do not imply precise position percentages unless the user asks for them.
- If the user has not provided a risk budget, use a default framework such as `主仓候选 70% total`, `观察仓 30% total`, `排除名单 0%`, then split each bucket by relative rank strength.
- Make it clear which symbol is suitable for `高权重主仓`, which only deserves `低权重观察`, and which should stay at `0%`.
- Comparison output should also show each symbol's daily-data freshness/source metadata when available.

---

### Step 7 — Event-Aware Risk Overlay

See **`scripts/events.py`** — `fetch_events(lookback_days, lookahead_days, min_importance)` returns a list of formatted strings.

> `news_economic_baidu()` date column is `datetime.date` objects — compare natively. Data **lags 4–8 weeks**; `events.py` always appends a hardcoded China macro calendar (PMI, Two Sessions, earnings windows) regardless of API success.

```python
from scripts.events import fetch_events
event_lines = fetch_events()  # returns list[str] ready to print
```

Overlay on analysis:
- Note any major macro event dates near current price levels.
- Flag the applicable earnings season window relative to today.
- Highlight price behavior around large news days visible in the K-line.

If event API is unavailable, note it and manually annotate the known calendar dates above.

---

### Step 8 — Deliver Structured Output

Return in this exact order:

```
[Symbol Summary]
名称/代码:           e.g. 贵州茅台 (600519) · A-Share Shanghai
分析区间:            2025-09-12 → 2026-03-12 (daily 6M, qfq-adjusted)
多周期确认:          Weekly trend: Uptrend | Monthly trend: Consolidation

[K-Line Snapshot]
最新收盘:           ¥1,580.00
1日涨跌:           +1.2% (+18.80)
MA5 / MA20 / MA60: ¥1,572 / ¥1,540 / ¥1,490   (排列多头 Bullish stack)
布林带 Bollinger:  Upper ¥1,640 | Mid ¥1,540 | Lower ¥1,440  (Width: 12.7%)
ATR-14 (波动幅):   ¥22.4 / day  (1.4% of price — moderate volatility)
20日区间:           ¥1,420 – ¥1,610
成交量 vs 20日均:   +35%  (放量)

[Technical View — 技术面]
趋势 Trend:         Daily Uptrend — MA5 > MA20 > MA60, price above all MAs
                    Weekly confirm: above weekly MA20 ✓
                    Monthly confirm: testing monthly MA20 resistance ⚠
动量 Momentum:     5D: +3.1% | 10D: +5.8% | 20D: +8.2% | Ann.Vol: 18%
MACD:              MACD line above signal, histogram expanding → bullish momentum
RSI-14:            68 — approaching overbought; momentum still intact
布林挤压 BB Squeeze: Width 12.7% — expanding (breakout in progress, not overextended)
支撑 Support:      ¥1,490 (MA60 + BB lower + prior swing low)
阻力 Resistance:   ¥1,640 (BB upper) / ¥1,650 (6M high zone)
ATR止损参考:       Trailing stop = last close − 1.5×ATR = ¥1,580 − ¥33.6 ≈ ¥1,546

[Valuation — 估值]
PE (TTM):          28x — 3-year 40th percentile (moderate)
PB:                8.2x
行业 PE 中位:      25x (white spirits industry) → slight premium to peers

[Relative Strength]  (if multi-symbol mode)
Symbol   6M Return  Vol    Sharpe  RSI   ATR%   Rank
600519   +22%       18%    1.22    68    1.4%   1st ← Leader
000858   +14%       21%    0.67    55    1.7%   2nd

[Leader Plan — 强者执行计划]
标的:              600519
试错区 / 确认区 / 突破区
止损:              trailing / structural

[Laggard Plan — 弱者执行计划]
标的:              000858
试错区 / 确认区 / 突破区
止损:              trailing / structural

[Priority Guidance — 统一优先级建议]   (if 3+ symbols)
右侧优先:          strongest bucket for right-side confirmation focus
只配观察:          mid bucket; watch only until structure improves
应回避:            weakest bucket; avoid unless a separate setup forms

[Portfolio Suggestion — 组合建议版]   (if 3+ symbols)
主仓候选:          top bucket from composite ranking
观察仓:            middle bucket
排除名单:          weakest bucket
主仓首选:          the single strongest symbol in the ranking
权重说明:          indicative allocation only, unless the user provides explicit risk budget

[Cache Freshness — 缓存时效]
来源:              实时抓取 / 本地缓存回退
最近K线日期:       last bar date
缓存文件时间:       cache file timestamp

[Event Overlay — 事件]
- 2026-03-15: NPC economic policy announcement (macro risk)
- 2026-04-30: Q1 earnings release window (re-rating trigger)
- No major gap days observed in 6M K-line window.

[Risk & Watchpoints — 风险]
- 多单失效: If price closes below MA20 (¥1,540) on volume → trend weakening
- 布林下轨破位: Price below BB lower (¥1,440) = volatility expansion to downside
- 超买风险: RSI near 70; daily overbought but weekly RSI 58 = room still exists
- ATR止损: Position sizing reference — 1 ATR = ¥22.4; adjust size accordingly
- 突破条件: Break above BB upper (¥1,640) + volume >+50% avg → momentum continuation
```

### Step 9 — Optional Execution Output

If the user asks for any of the following, append an execution-focused section after the structured report:
- "压缩成交易视角"
- "入场位 / 止损位 / 观察位"
- "短线 T+波段方案"
- "明天开盘怎么挂单"
- "三段式盯盘清单"
- "尾盘买还是早盘买"

Generate these sections from the actual computed values; do not hand-wave or hardcode levels.

Required subsections:

```text
[Trading Plan — 交易执行版]
试错低吸区:      derived from support / ATR / recent price, marked as small-size only
右侧确认区:      around MA20 recovery zone
突破跟随区:      around resistance / BB upper breakout zone
试错止损:        around trailing stop (e.g. last close − 1.5×ATR)
结构止损:        support / BB lower invalidation
观察主线:        first recover MA20, then break resistance with volume

[Watchlist — 三段式盯盘清单]
开盘前:          key price lines, default no first-bar chase
盘中:            what qualifies for low-risk add vs no-trade
收盘前:          whether right-side confirmation is valid on close

[Timing Bias — 早盘 vs 尾盘]
执行偏好:        choose open-only for strong multi-timeframe trends; otherwise prefer close confirmation
原因:            explicitly explain whether the stock is trend-aligned or still weak-repair
```

Decision rule for `早盘买还是尾盘买`:
- If daily/weekly/monthly are not aligned bullish, default to **尾盘优先** and describe early-buy as trial-only.
- If daily plus weekly are already strong and resistance has just been reclaimed on volume, early participation can be allowed.
- Never present either choice as guaranteed superior; explain the condition set.

## Quality Criteria

- Market mapping is stated and auditable.
- All indicator values are computed from actual fetched data, not estimated.
- Valuation section states data source and percentile basis.
- Event overlay explicitly covers ±30 days around analysis date.
- No language implying guaranteed price direction or investment advice.
- If any section fails (e.g. valuation API times out), skip it with an explicit note.
- Execution sections must be derived from actual MA/BB/ATR/support/resistance values from the fetched dataset.
- Distinguish clearly between `试错` and `确认`; do not blur left-side and right-side entries.
- In comparison mode, the report must tell the user which symbol has higher trading priority and which symbol should be treated as laggard / lower-priority.
- Cache fallback must never silently fabricate data; it may only reuse the most recent successfully fetched local frame.
- If cached data is used, the report must make that visible in either a `Data Freshness` or `Cache Freshness` section.
- In portfolio suggestion mode, the report should expose suggested weights at the symbol level when there are multiple candidates in the same bucket.

## Example Prompts

- "Use stock-kline-analysis to analyze 600519."
- "Use stock-kline-analysis for 贵州茅台 — show K-line with Bollinger Bands, MACD, RSI, and ATR stop-loss."
- "Use stock-kline-analysis on AAPL — multi-timeframe trend: are daily/weekly/monthly aligned?"
- "Use stock-kline-analysis to compare 600036 and 601318 by relative strength and ATR-based risk."
- "Use stock-kline-analysis for 000858 — show Bollinger squeeze and flag any upcoming earnings event."
- "Use stock-kline-analysis for TSLA — is price near Bollinger upper band? What does ATR say about position sizing?"
- "Use stock-kline-analysis for 贵州茅台 — 压缩成交易视角，给我入场位、止损位、观察位。"
- "Use stock-kline-analysis for 贵州茅台 — 写成明天开盘怎么挂单的执行版。"
- "Use stock-kline-analysis for 贵州茅台 — 输出开盘前、盘中、收盘前三段式盯盘清单。"
- "Use stock-kline-analysis for 贵州茅台 — 现在更适合尾盘买还是早盘买？给条件判断。"
- "Use stock-kline-analysis to compare 贵州茅台 and 五粮液, then output a relative-strength execution plan with leader and laggard trade plans."
- "Use stock-kline-analysis for 600519 000858 601318 — rank them by relative strength and tell me which one deserves right-side priority."
- "Use stock-kline-analysis for 贵州茅台 五粮液 泸州老窖 — tell me who deserves right-side priority, who is watch-only, and who should be avoided."
- "Use stock-kline-analysis for 贵州茅台 五粮液 泸州老窖 — give me a portfolio suggestion with main position candidates, watchlist names, and exclusions, and show cache freshness if fallback data is used."
- "Use stock-kline-analysis for 贵州茅台 五粮液 泸州老窖 山西汾酒 — give me a portfolio suggestion with indicative weights, telling me which one deserves higher main-position weight and which ones only deserve low-weight observation."

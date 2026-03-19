"""
run_analysis.py — End-to-end orchestrator for the stock-kline-analysis skill.

Runs Steps 1–8: resolve → fetch → indicators → chart → valuation → events → output.

Usage:
    python run_analysis.py 000063
    python run_analysis.py 贵州茅台
    python run_analysis.py AAPL
    python run_analysis.py 000063 --out-dir /tmp/reports
"""

from __future__ import annotations

import argparse
import sys
import os
import math
import numpy as np
from functools import lru_cache
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Allow running from any working directory
_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import akshare as ak
from fetch_kline  import fetch_all_timeframes
from indicators   import add_indicators, add_tf_indicators
from chart        import plot_kline
from valuation    import fetch_valuation, compute_pe_pb
from events       import fetch_events


_SYM_FILE = _SCRIPTS_DIR / "data" / "a_share_symbols.csv"


@lru_cache(maxsize=1)
def _get_a_symbol_list():
    """Load A-share code↔name map from the bundled local CSV (no network needed)."""
    import pandas as pd
    return pd.read_csv(_SYM_FILE, dtype=str)


def refresh_symbol_list():
    """One-time helper: fetch latest SH+SZ symbol lists and overwrite the local CSV."""
    import pandas as pd
    from akshare.stock.stock_info import stock_info_sh_name_code, stock_info_sz_name_code

    frames = []
    sh = stock_info_sh_name_code()
    frames.append(sh.rename(columns={"证券代码": "code", "证券简称": "name"})[["code", "name"]])
    sz = stock_info_sz_name_code()
    frames.append(sz.rename(columns={"A股代码": "code", "A股简称": "name"})[["code", "name"]])

    df = pd.concat(frames, ignore_index=True)
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["name"] = df["name"].str.strip()
    _SYM_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_SYM_FILE, index=False, encoding="utf-8")
    print(f"[symbols] Refreshed {len(df)} symbols → {_SYM_FILE}")
    _get_a_symbol_list.cache_clear()


# ────────────────────────────────────────────────────────────────────────────
# Step 1 — Resolve Identifier
# ────────────────────────────────────────────────────────────────────────────

def resolve_symbol(raw: str) -> tuple[str, str, str]:
    """
    Return (code, name, market_label).

    Auto-detection rules:
      6-digit starting with 6      → A-share Shanghai
      6-digit starting with 0 or 3 → A-share Shenzhen
      5-digit starting with 0      → HK
      letters (4-5 chars)          → US
      otherwise                    → search A-share name list
    """
    raw = raw.strip()

    # Purely numeric
    if raw.isdigit():
        if len(raw) == 6:
            if raw.startswith("6"):
                market = "A股上交所"
            else:
                market = "A股深交所"
            # Confirm name via symbol list
            try:
                sym_df = _get_a_symbol_list()
                hit = sym_df[sym_df["code"] == raw]
                name = hit["name"].iloc[0] if not hit.empty else raw
            except Exception:
                name = raw
            return raw, name, market
        if len(raw) == 5 and raw.startswith("0"):
            return raw, raw, "港股 HK"

    # ASCII letters → US ticker
    if raw.isascii() and raw.isalpha() and 1 <= len(raw) <= 5:
        return raw.upper(), raw.upper(), "美股 US"

    # Chinese name → search A-share list
    try:
        sym_df = _get_a_symbol_list()
        # Exact match first, then substring
        exact = sym_df[sym_df["name"] == raw]
        if not exact.empty:
            code = exact["code"].iloc[0]
            return resolve_symbol(code)  # re-enter with numeric code
        partial = sym_df[sym_df["name"].str.contains(raw, na=False)]
        if len(partial) == 1:
            code = partial["code"].iloc[0]
            return resolve_symbol(code)
        if len(partial) > 1:
            candidates = partial.head(3)[["code", "name"]].to_string(index=False)
            raise ValueError(
                f"Ambiguous name '{raw}'. Top matches:\n{candidates}\n"
                "Please re-run with the exact 6-digit code."
            )
    except ValueError:
        raise
    except Exception as e:
        print(f"[resolve] Symbol list lookup failed: {e}")

    raise ValueError(f"Cannot resolve '{raw}' to a known stock symbol.")


# ────────────────────────────────────────────────────────────────────────────
# Step 8 — Format structured output
# ────────────────────────────────────────────────────────────────────────────

def _pct(val) -> str:
    return f"{val:+.1f}%" if val is not None and not np.isnan(val) else "N/A"


def _fmt(val, decimals=2, prefix="¥") -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{prefix}{val:.{decimals}f}"


def _format_range(low: float, high: float) -> str:
    if low > high:
        low, high = high, low
    return f"¥{low:.2f} – ¥{high:.2f}"


def _clamp_zone(low: float, high: float, fallback: float) -> tuple[float, float]:
    if low > high:
        span = max(abs(fallback) * 0.01, 1.0)
        return fallback - span, fallback + span
    return low, high


def build_trade_plan(df_daily, df_weekly, df_monthly) -> dict:
    last = df_daily.iloc[-1]
    support = float(df_daily.attrs.get("support", last["bb_lower"]))
    resistance = float(df_daily.attrs.get("resistance", last["bb_upper"]))
    atr = float(last["atr14"])
    last_close = float(last["close"])
    ma5 = float(last["ma5"])
    ma20 = float(last["ma20"])

    aggressive_low = max(support + 1.2 * atr, last_close - 1.0 * atr)
    aggressive_high = min(last_close - 0.2 * atr, ma5 + 0.2 * atr)
    aggressive_low, aggressive_high = _clamp_zone(aggressive_low, aggressive_high, last_close - 0.5 * atr)

    confirm_low = ma20
    confirm_high = ma20 + 0.7 * atr
    breakout_low = resistance
    breakout_high = resistance + 0.8 * atr

    trailing_stop = last_close - 1.5 * atr
    confirm_stop = ma20 - 1.3 * atr
    breakout_stop = resistance - 1.7 * atr

    weekly_bias = None
    if df_weekly is not None and "ma20" in df_weekly.columns:
        weekly_last = df_weekly.iloc[-1]
        weekly_bias = bool(weekly_last["close"] > weekly_last["ma20"])

    monthly_bias = None
    if df_monthly is not None and "ma20" in df_monthly.columns:
        monthly_last = df_monthly.iloc[-1]
        monthly_bias = bool(monthly_last["close"] > monthly_last["ma20"])

    ma_bull = bool(last_close > ma5 > ma20 > float(last["ma60"])) if not any(np.isnan(v) for v in [ma5, ma20, last["ma60"]]) else False
    close_preferred = not ma_bull or weekly_bias is False or monthly_bias is False

    return {
        "aggressive_zone": (aggressive_low, aggressive_high),
        "confirm_zone": (confirm_low, confirm_high),
        "breakout_zone": (breakout_low, breakout_high),
        "invalidation": trailing_stop,
        "structural_stop": support,
        "confirm_stop": confirm_stop,
        "breakout_stop": breakout_stop,
        "confirm_line": ma20,
        "breakout_line": resistance,
        "close_preferred": close_preferred,
    }


def build_execution_sections(df_daily, df_weekly, df_monthly) -> list[str]:
    last = df_daily.iloc[-1]
    plan = build_trade_plan(df_daily, df_weekly, df_monthly)
    aggressive_low, aggressive_high = plan["aggressive_zone"]
    confirm_low, confirm_high = plan["confirm_zone"]
    breakout_low, breakout_high = plan["breakout_zone"]
    volume_ratio = float(last["volume"] / df_daily["volume"].tail(20).mean())
    early_buy_bias = "尾盘优先，早盘只适合小仓试错" if plan["close_preferred"] else "可早盘跟随，但仍需量价确认"
    close_bias_reason = "周/月级别尚未共振转强，尾盘更能确认是假反抽还是修复成立" if plan["close_preferred"] else "多周期偏强，早盘顺势参与的容错更高"

    return [
        "",
        "[Trading Plan — 交易执行版]",
        f"  试错低吸区   : {_format_range(aggressive_low, aggressive_high)}  (仅小仓)" ,
        f"  右侧确认区   : {_format_range(confirm_low, confirm_high)}  (站稳 MA20 后加仓)",
        f"  突破跟随区   : {_format_range(breakout_low, breakout_high)}  (放量突破阻力后处理为趋势单)",
        f"  试错止损     : ¥{plan['invalidation']:.2f}",
        f"  结构止损     : ¥{plan['structural_stop']:.2f}",
        f"  确认仓止损   : ¥{plan['confirm_stop']:.2f}",
        f"  突破仓止损   : ¥{plan['breakout_stop']:.2f}",
        f"  观察主线     : 先看 ¥{plan['confirm_line']:.2f} 能否收回，再看 ¥{plan['breakout_line']:.2f} 能否放量突破",
        "",
        "[Watchlist — 三段式盯盘清单]",
        "  开盘前       : 写好试错区、确认线、失效线；默认不开盘追第一笔",
        f"                 重点价格 = {_format_range(aggressive_low, aggressive_high)} / ¥{plan['confirm_line']:.2f} / ¥{plan['structural_stop']:.2f}",
        f"  盘中         : 若回踩试错区止跌可小仓参与；若站上 ¥{plan['confirm_line']:.2f} 且量能改善，再考虑加仓",
        f"                 当前量能参考 = {(volume_ratio - 1) * 100:+.0f}% vs 20日均量",
        f"  收盘前       : 只有收盘稳在 ¥{plan['confirm_line']:.2f} 上方，右侧修复逻辑才成立；否则按反抽看待",
        "",
        "[Timing Bias — 早盘 vs 尾盘]",
        f"  执行偏好     : {early_buy_bias}",
        f"  原因         : {close_bias_reason}",
        f"  早盘买条件   : 仅在 {_format_range(aggressive_low, aggressive_high)} 一带止跌时小仓试错，不追高",
        f"  尾盘买条件   : 收盘前稳定在 ¥{plan['confirm_line']:.2f} 上方，且回落不破，优先尾盘确认单",
    ]


def _annualized_volatility(df_daily, window: int = 20) -> float:
    return float(df_daily["close"].pct_change().tail(window).std() * np.sqrt(252) * 100)


def _return_pct(df_daily) -> float:
    return float((df_daily["close"].iloc[-1] / df_daily["close"].iloc[0] - 1) * 100)


def _ordinal(rank: int) -> str:
    if 10 <= rank % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"{rank}{suffix}"


def _priority_label(rank: int, total: int) -> str:
    if total <= 2:
        return "右侧优先" if rank == 1 else "应回避"

    top_count = max(1, math.ceil(total / 3))
    bottom_count = max(1, total // 3)
    if top_count + bottom_count >= total:
        bottom_count = 1

    if rank <= top_count:
        return "右侧优先"
    if rank > total - bottom_count:
        return "应回避"
    return "只配观察"


def _format_symbol_group(items: list[dict[str, Any]]) -> str:
    if not items:
        return "无"
    return " / ".join(f"{item['name']} ({item['code']})" for item in items)


def _bucket_weight_total(bucket: str) -> int:
    if bucket == "右侧优先":
        return 70
    if bucket == "只配观察":
        return 30
    return 0


def _assign_allocation_weights(ranked: list[dict[str, Any]]) -> None:
    buckets = {
        "右侧优先": [item for item in ranked if item["priority"] == "右侧优先"],
        "只配观察": [item for item in ranked if item["priority"] == "只配观察"],
        "应回避": [item for item in ranked if item["priority"] == "应回避"],
    }

    for bucket, items in buckets.items():
        total_weight = _bucket_weight_total(bucket)
        if not items or total_weight == 0:
            for item in items:
                item["suggested_weight"] = 0
                item["weight_role"] = "排除"
            continue

        scores = [max(1, len(ranked) + 1 - item["rank"]) for item in items]
        score_sum = sum(scores)
        allocated = 0
        for idx, item in enumerate(items):
            if idx == len(items) - 1:
                weight = total_weight - allocated
            else:
                weight = round(total_weight * scores[idx] / score_sum)
                allocated += weight
            item["suggested_weight"] = weight
            if bucket == "右侧优先":
                item["weight_role"] = "高权重主仓" if weight >= 40 else "中权重主仓"
            elif bucket == "只配观察":
                item["weight_role"] = "低权重观察"
            else:
                item["weight_role"] = "排除"


def _format_weight_group(items: list[dict[str, Any]]) -> str:
    if not items:
        return "无"
    return " / ".join(
        f"{item['name']} ({item['code']}) {item.get('suggested_weight', 0)}%"
        for item in items
    )


def _fetch_meta_line(df, label: str = "日线") -> str | None:
    meta = df.attrs.get("fetch_meta") if hasattr(df, "attrs") else None
    if not meta:
        return None

    source_label = "实时抓取" if meta.get("source") == "live" else "本地缓存回退"
    staleness = meta.get("staleness_days")
    staleness_text = f"距今天 {staleness} 天" if staleness is not None else "时效未知"
    caution = " ⚠ 缓存较旧" if meta.get("source") == "cache" and staleness is not None and staleness > 5 else ""
    return (
        f"  {label}数据      : {source_label} | last bar {meta.get('last_bar_date', 'N/A')} | "
        f"cache {meta.get('cache_file', 'N/A')} @ {meta.get('cached_at', 'N/A')} | {staleness_text}{caution}"
    )


def _preserve_attrs(target_df, original_attrs: dict[str, Any]):
    target_df.attrs.update(original_attrs)
    return target_df


def analyze_symbol(
    raw_input: str,
    out_dir: Path,
    output_mode: str,
    render_chart: bool = True,
    include_context: bool = True,
) -> dict[str, Any]:
    print(f"[run] Resolving '{raw_input}' ...")
    code, name, market_label = resolve_symbol(raw_input)
    print(f"[run] → {name} ({code}) · {market_label}")

    print("[run] Fetching K-line data ...")
    df_daily, df_weekly, df_monthly = fetch_all_timeframes(code)
    daily_attrs = dict(df_daily.attrs)
    weekly_attrs = dict(df_weekly.attrs) if df_weekly is not None else {}
    monthly_attrs = dict(df_monthly.attrs) if df_monthly is not None else {}

    print("[run] Computing indicators ...")
    df_daily = add_indicators(df_daily)
    df_weekly, df_monthly = add_tf_indicators(df_weekly, df_monthly)
    _preserve_attrs(df_daily, daily_attrs)
    if df_weekly is not None:
        _preserve_attrs(df_weekly, weekly_attrs)
    if df_monthly is not None:
        _preserve_attrs(df_monthly, monthly_attrs)

    chart_path = None
    if render_chart:
        chart_path = str(out_dir / f"{code}_kline.png")
        print("[run] Rendering chart ...")
        plot_kline(df_daily, code=code, name=name, market_label=market_label, out_path=chart_path)

    if include_context:
        print("[run] Fetching valuation ...")
        try:
            val = fetch_valuation(code)
            val = compute_pe_pb(val, last_close=float(df_daily["close"].iloc[-1]))
        except Exception as exc:
            val = {"note": f"valuation unavailable: {exc}"}

        print("[run] Fetching events ...")
        try:
            event_lines = fetch_events()
        except Exception as exc:
            event_lines = [f"- Event data unavailable: {exc}"]
    else:
        val = {"note": "valuation skipped in relative-strength mode"}
        event_lines = ["- Event overlay skipped in relative-strength mode"]

    report = format_output(
        code, name, market_label,
        df_daily, df_weekly, df_monthly,
        val, event_lines,
        output_mode=output_mode,
    )

    return {
        "raw_input": raw_input,
        "code": code,
        "name": name,
        "market_label": market_label,
        "df_daily": df_daily,
        "df_weekly": df_weekly,
        "df_monthly": df_monthly,
        "val": val,
        "event_lines": event_lines,
        "report": report,
        "chart_path": chart_path,
    }


def build_relative_strength_data(symbol_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for report in symbol_reports:
        df_daily = report["df_daily"]
        ret = _return_pct(df_daily)
        vol = _annualized_volatility(df_daily, window=20)
        sharpe_proxy = ret / vol if vol and not np.isnan(vol) else np.nan
        last = df_daily.iloc[-1]
        metrics.append(
            {
                "code": report["code"],
                "name": report["name"],
                "market_label": report["market_label"],
                "return_6m": ret,
                "vol_20d": vol,
                "sharpe_proxy": sharpe_proxy,
                "rsi14": float(last["rsi14"]),
                "atr_pct": float(last["atr_pct"]),
                "plan": build_trade_plan(report["df_daily"], report["df_weekly"], report["df_monthly"]),
                "report": report,
            }
        )

    rank_fields = [
        ("return_6m", True),
        ("sharpe_proxy", True),
        ("rsi14", True),
        ("atr_pct", False),
    ]
    for metric, descending in rank_fields:
        ordered = sorted(
            metrics,
            key=lambda item: item[metric] if not np.isnan(item[metric]) else (-np.inf if descending else np.inf),
            reverse=descending,
        )
        for idx, item in enumerate(ordered, start=1):
            item.setdefault("rank_score", 0)
            item["rank_score"] += idx

    ordered_final = sorted(metrics, key=lambda item: (item["rank_score"], -item["return_6m"]))
    for idx, item in enumerate(ordered_final, start=1):
        item["rank"] = idx
    return ordered_final


def _trade_plan_summary_lines(title: str, item: dict[str, Any]) -> list[str]:
    plan = item["plan"]
    aggressive_low, aggressive_high = plan["aggressive_zone"]
    confirm_low, confirm_high = plan["confirm_zone"]
    breakout_low, breakout_high = plan["breakout_zone"]
    bias = "尾盘确认优先" if plan["close_preferred"] else "可早盘跟随"
    return [
        "",
        title,
        f"  标的         : {item['name']} ({item['code']})",
        f"  试错区       : {_format_range(aggressive_low, aggressive_high)}",
        f"  确认区       : {_format_range(confirm_low, confirm_high)}",
        f"  突破区       : {_format_range(breakout_low, breakout_high)}",
        f"  试错止损     : ¥{plan['invalidation']:.2f}",
        f"  结构止损     : ¥{plan['structural_stop']:.2f}",
        f"  执行偏好     : {bias}",
        f"  观察主线     : 先看 ¥{plan['confirm_line']:.2f}，再看 ¥{plan['breakout_line']:.2f}",
    ]


def format_compare_output(symbol_reports: list[dict[str, Any]], output_mode: str = "structured") -> str:
    ranked = build_relative_strength_data(symbol_reports)
    leader = ranked[0]
    laggard = ranked[-1]
    total = len(ranked)
    start_date = max(report["df_daily"]["date"].iloc[0] for report in symbol_reports)
    today = date.today()
    compared_symbols = " / ".join(f"{item['name']} ({item['code']})" for item in ranked)

    for item in ranked:
        item["priority"] = _priority_label(item["rank"], total)

    _assign_allocation_weights(ranked)

    priority_items = [item for item in ranked if item["priority"] == "右侧优先"]
    watch_items = [item for item in ranked if item["priority"] == "只配观察"]
    avoid_items = [item for item in ranked if item["priority"] == "应回避"]

    lines = [
        "",
        "═" * 72,
        "  Relative Strength 对比报告",
        "═" * 72,
        "",
        "[Comparison Summary]",
        f"  对比标的     : {compared_symbols}",
        f"  分析区间     : {start_date} → {today} (日线 6M, qfq-adjusted where applicable)",
        f"  Relative Leader : {leader['name']} ({leader['code']})",
        f"  Relative Laggard: {laggard['name']} ({laggard['code']})",
        "",
        "[Relative Strength]",
        "  Symbol                 6M Return   Vol20D   Sharpe   RSI14   ATR%   Rank   View       Weight",
    ]

    for item in ranked:
        label = f"{item['name']} ({item['code']})"
        marker = " ← Leader" if item is leader else " ← Laggard" if item is laggard else ""
        lines.append(
            f"  {label:<22} {item['return_6m']:>8.1f}%  {item['vol_20d']:>7.1f}%  {item['sharpe_proxy']:>6.2f}  {item['rsi14']:>5.1f}  {item['atr_pct']:>5.1f}%   {_ordinal(item['rank']):<5} {item['priority']:<8} {item.get('suggested_weight', 0):>3}%{marker}"
        )

    lines += [
        "",
        "[Execution Bias — 相对强弱执行结论]",
        f"  Leader 优先级 : {leader['name']} 更适合做右侧确认或突破跟随，因其 return / Sharpe / RSI 综合更强",
        f"  Laggard 处理  : {laggard['name']} 只适合超跌反抽试错，若不能收回确认线则应降低优先级",
    ]

    if total >= 3:
        lines += [
            "",
            "[Priority Guidance — 统一优先级建议]",
            f"  右侧优先     : {_format_symbol_group(priority_items)}",
            f"  只配观察     : {_format_symbol_group(watch_items)}",
            f"  应回避       : {_format_symbol_group(avoid_items)}",
        ]
        lines += [
            "",
            "[Portfolio Suggestion — 组合建议版]",
            f"  主仓候选     : {_format_weight_group(priority_items)}",
            f"  观察仓       : {_format_weight_group(watch_items)}",
            f"  排除名单     : {_format_weight_group(avoid_items)}",
            f"  主仓首选     : {leader['name']} ({leader['code']})",
            "  权重说明     : 为相对强弱排序下的组合建议，不是精确仓位模型；若用户未提供风险预算，默认主仓70% / 观察30% / 排除0% 的框架。",
        ]
        if leader["return_6m"] < 0:
            lines.append("  提醒         : 即使相对最强标的仍为负收益，右侧优先也仅代表相对占优，不代表趋势已确认。")

    freshness_lines = [
        _fetch_meta_line(item["report"]["df_daily"], label=f"{item['name']}日线")
        for item in ranked
    ]
    freshness_lines = [line for line in freshness_lines if line]
    if freshness_lines:
        lines += ["", "[Cache Freshness — 缓存时效]"]
        lines += freshness_lines

    if output_mode in {"full", "execution"}:
        lines += _trade_plan_summary_lines("[Leader Plan — 强者执行计划]", leader)
        lines += _trade_plan_summary_lines("[Laggard Plan — 弱者执行计划]", laggard)

    lines += [
        "",
        "  ⚠ 本报告仅供信息参考，不构成任何投资建议。",
        "═" * 72,
        "",
    ]
    return "\n".join(lines)


def format_output(
    code: str, name: str, market_label: str,
    df_daily, df_weekly, df_monthly,
    val: dict,
    event_lines: list[str],
    output_mode: str = "structured",
) -> str:
    last   = df_daily.iloc[-1]
    prev   = df_daily.iloc[-2]
    today  = date.today()

    pct_chg  = (last["close"] - prev["close"]) / prev["close"] * 100
    abs_chg  = last["close"] - prev["close"]
    vol_avg20 = df_daily["volume"].tail(20).mean()
    vol_ratio = last["volume"] / vol_avg20

    r5   = (last["close"] / df_daily["close"].iloc[-6]  - 1) * 100
    r10  = (last["close"] / df_daily["close"].iloc[-11] - 1) * 100
    r20  = (last["close"] / df_daily["close"].iloc[-21] - 1) * 100
    ann_vol = df_daily["close"].pct_change().tail(60).std() * np.sqrt(252) * 100

    high20 = df_daily["high"].tail(20).max()
    low20  = df_daily["low"].tail(20).min()

    ma_bull = (
        last["close"] > last["ma5"] > last["ma20"] > last["ma60"]
        if not any(np.isnan(v) for v in [last["ma5"], last["ma20"], last["ma60"]])
        else False
    )
    ma_stack = "排列多头 Bullish stack" if ma_bull else "空头排列 Bearish stack"

    # Multi-timeframe
    w_trend = m_trend = "N/A"
    if df_weekly is not None and "ma20" in df_weekly.columns:
        wl = df_weekly.iloc[-1]
        w_trend = "Uptrend ✓" if wl["close"] > wl["ma20"] else "Downtrend ✗"
    if df_monthly is not None and "ma20" in df_monthly.columns:
        ml = df_monthly.iloc[-1]
        m_trend = "Uptrend ✓" if ml["close"] > ml["ma20"] else "Holding Support (above MA20) ✓" \
            if ml["close"] >= ml["ma20"] * 0.98 else "Downtrend ✗"

    # MACD direction
    hist_last5 = df_daily["macd_hist"].tail(5).tolist()
    macd_desc = (
        "MACD & Signal below zero; histogram converging → bearish momentum fading"
        if last["macd"] < 0 and abs(last["macd_hist"]) < 0.05
        else "MACD above Signal, histogram positive → bullish momentum"
        if last["macd"] > last["macd_signal"] and last["macd_hist"] > 0
        else "MACD below Signal, histogram negative → bearish momentum"
    )

    # BB squeeze
    bb_desc = (
        "Squeeze — band narrowing, breakout pending"
        if last["bb_width"] < 10
        else "Expanding — volatility breakout in progress"
        if last["bb_width"] > 20
        else "Normal bandwidth"
    )

    trailing_stop = last["close"] - 1.5 * last["atr14"]

    start_date = df_daily["date"].iloc[0]

    lines = [
        "",
        "═" * 65,
        f"  {name} ({code}) · K线分析报告",
        "═" * 65,
        "",
        "[Symbol Summary]",
        f"  名称/代码   : {name} ({code}) · {market_label}",
        f"  分析区间   : {start_date} → {today} (日线 6M, 前复权 qfq)",
        f"  多周期确认 : Weekly: {w_trend}  |  Monthly: {m_trend}",
        "",
        "[K-Line Snapshot]",
        f"  最新收盘         : ¥{last['close']:.2f}",
        f"  1日涨跌          : {pct_chg:+.2f}%  ({abs_chg:+.2f})",
        f"  MA5 / MA20 / MA60: ¥{last['ma5']:.2f} / ¥{last['ma20']:.2f} / ¥{last['ma60']:.2f}  ({ma_stack})",
        f"  布林带 Bollinger : Upper ¥{last['bb_upper']:.2f} | Mid ¥{last['bb_mid']:.2f} | Lower ¥{last['bb_lower']:.2f}  (Width: {last['bb_width']:.1f}%)",
        f"  ATR-14 (波动幅)  : ¥{last['atr14']:.2f}/day  ({last['atr_pct']:.1f}% of price)",
        f"  20日区间         : ¥{low20:.2f} – ¥{high20:.2f}",
        f"  成交量 vs 20日均 : {(vol_ratio-1)*100:+.0f}%  ({'放量' if vol_ratio > 1.2 else '缩量' if vol_ratio < 0.8 else '平量'})",
        "",
        "[Technical View — 技术面]",
        f"  趋势 Trend   : {ma_stack}",
        f"                 Weekly: {w_trend}",
        f"                 Monthly: {m_trend}",
        f"  动量 Momentum: 5D {_pct(r5)} | 10D {_pct(r10)} | 20D {_pct(r20)} | Ann.Vol {ann_vol:.1f}%",
        f"  MACD         : {macd_desc}",
        f"                 Hist(last 5): {[round(h,4) for h in hist_last5]}",
        f"  RSI-14       : {last['rsi14']:.1f}  ({'超买 overbought' if last['rsi14']>70 else '超卖 oversold' if last['rsi14']<30 else '中性 neutral'})",
        f"  BB Squeeze   : Width {last['bb_width']:.1f}% — {bb_desc}",
        f"  支撑 Support : ¥{df_daily.attrs.get('support', 0):.2f}",
        f"  阻力 Resist  : ¥{df_daily.attrs.get('resistance', 0):.2f}",
        f"  ATR止损参考  : last close − 1.5×ATR = ¥{last['close']:.2f} − ¥{1.5*last['atr14']:.2f} ≈ ¥{trailing_stop:.2f}",
    ]

    # Valuation
    lines += ["", "[Valuation — 估值]"]
    if val.get("note"):
        lines.append(f"  Note      : {val['note']}")
    if val.get("pe_ttm") is not None:
        lines.append(f"  PE (TTM)  : {val['pe_ttm']}x  (EPS ¥{val.get('eps','N/A')})")
    else:
        lines.append("  PE (TTM)  : N/A (EPS unavailable)")
    if val.get("pb") is not None:
        lines.append(f"  PB        : {val['pb']}x  (BVPS ¥{val.get('book_value_per_share','N/A')})")
    lines += [
        f"  ROE       : {val.get('roe','N/A')}%",
        f"  毛利率    : {val.get('gross_margin','N/A')}%",
        f"  营收 YoY  : {_pct(val.get('revenue_yoy'))}",
        f"  净利 YoY  : {_pct(val.get('net_profit_yoy'))}",
        f"  行业      : {val.get('industry','N/A')}",
        f"  最新公告  : {val.get('report_date','N/A')}",
        "  (历史PE百分位: 不可用 — stock_a_lg_indicator 接口已下线)",
    ]

    # Events
    lines += ["", "[Event Overlay — 事件]"]
    lines += event_lines

    freshness_line = _fetch_meta_line(df_daily)
    if freshness_line:
        lines += ["", "[Data Freshness — 数据时效]", freshness_line]

    # Risk
    lines += [
        "",
        "[Risk & Watchpoints — 风险]",
        f"  多单失效   : 若收盘跌破 MA20 (¥{last['ma20']:.2f}) + 放量 → 趋势走弱",
        f"  布林下轨   : 跌破 BB Lower (¥{last['bb_lower']:.2f}) = 下行波动放大",
        f"  RSI超买    : RSI {last['rsi14']:.1f}{'  — 接近超买，注意回调' if last['rsi14'] > 65 else '  — 中性区，无明显超买'}",
        f"  ATR止损    : 仓位管理参考 1 ATR = ¥{last['atr14']:.2f}",
        f"  突破条件   : 重返 MA20 (¥{last['ma20']:.2f}) + MACD金叉 + 成交量 >+50% → 反转确认",
        "",
        "  ⚠ 本报告仅供信息参考，不构成任何投资建议。",
        "═" * 65,
        "",
    ]

    if output_mode in {"full", "execution"}:
        lines = lines[:-3] + build_execution_sections(df_daily, df_weekly, df_monthly) + lines[-3:]

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# Markdown formatting
# ────────────────────────────────────────────────────────────────────────────

def _ts() -> str:
    """Compact timestamp for filenames: YYYYMMDD_HHMM."""
    return datetime.now().strftime("%Y%m%d_%H%M")


def _ts_full() -> str:
    """Human-readable timestamp for report header."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _md_meta(title: str) -> list[str]:
    return [
        "---",
        f"title: \"{title}\"",
        f"date: {_ts_full()}",
        "generator: stock-kline-analysis",
        "---",
        "",
    ]


def format_markdown(
    code: str, name: str, market_label: str,
    df_daily, df_weekly, df_monthly,
    val: dict,
    event_lines: list[str],
    output_mode: str = "structured",
    chart_path: str | None = None,
) -> str:
    """Produce a Markdown version of the single-stock report."""
    last   = df_daily.iloc[-1]
    prev   = df_daily.iloc[-2]
    today  = date.today()

    pct_chg  = (last["close"] - prev["close"]) / prev["close"] * 100
    abs_chg  = last["close"] - prev["close"]
    vol_avg20 = df_daily["volume"].tail(20).mean()
    vol_ratio = last["volume"] / vol_avg20

    r5   = (last["close"] / df_daily["close"].iloc[-6]  - 1) * 100
    r10  = (last["close"] / df_daily["close"].iloc[-11] - 1) * 100
    r20  = (last["close"] / df_daily["close"].iloc[-21] - 1) * 100
    ann_vol = df_daily["close"].pct_change().tail(60).std() * np.sqrt(252) * 100

    high20 = df_daily["high"].tail(20).max()
    low20  = df_daily["low"].tail(20).min()

    ma_bull = (
        last["close"] > last["ma5"] > last["ma20"] > last["ma60"]
        if not any(np.isnan(v) for v in [last["ma5"], last["ma20"], last["ma60"]])
        else False
    )
    ma_stack = "排列多头 Bullish stack" if ma_bull else "空头排列 Bearish stack"

    w_trend = m_trend = "N/A"
    if df_weekly is not None and "ma20" in df_weekly.columns:
        wl = df_weekly.iloc[-1]
        w_trend = "Uptrend ✓" if wl["close"] > wl["ma20"] else "Downtrend ✗"
    if df_monthly is not None and "ma20" in df_monthly.columns:
        ml = df_monthly.iloc[-1]
        m_trend = "Uptrend ✓" if ml["close"] > ml["ma20"] else "Holding Support (above MA20) ✓" \
            if ml["close"] >= ml["ma20"] * 0.98 else "Downtrend ✗"

    hist_last5 = df_daily["macd_hist"].tail(5).tolist()
    macd_desc = (
        "MACD & Signal below zero; histogram converging → bearish momentum fading"
        if last["macd"] < 0 and abs(last["macd_hist"]) < 0.05
        else "MACD above Signal, histogram positive → bullish momentum"
        if last["macd"] > last["macd_signal"] and last["macd_hist"] > 0
        else "MACD below Signal, histogram negative → bearish momentum"
    )

    bb_desc = (
        "Squeeze — band narrowing, breakout pending"
        if last["bb_width"] < 10
        else "Expanding — volatility breakout in progress"
        if last["bb_width"] > 20
        else "Normal bandwidth"
    )

    trailing_stop = last["close"] - 1.5 * last["atr14"]
    start_date = df_daily["date"].iloc[0]
    support = df_daily.attrs.get("support", 0)
    resistance = df_daily.attrs.get("resistance", 0)

    rsi_label = "超买 overbought" if last["rsi14"] > 70 else "超卖 oversold" if last["rsi14"] < 30 else "中性 neutral"
    vol_label = "放量" if vol_ratio > 1.2 else "缩量" if vol_ratio < 0.8 else "平量"

    lines = _md_meta(f"{name} ({code}) K线分析报告")
    lines += [
        f"# {name} ({code}) · K线分析报告",
        "",
        f"> 生成时间: {_ts_full()}  ",
        #f"> 数据来源: AkShare · 前复权 qfq  ",
        "",
        "## Symbol Summary",
        "",
        f"| 项目 | 内容 |",
        f"|---|---|",
        f"| 名称/代码 | {name} ({code}) · {market_label} |",
        f"| 分析区间 | {start_date} → {today} (日线 6M, qfq-adjusted) |",
        f"| 多周期确认 | Weekly: {w_trend} \\| Monthly: {m_trend} |",
        "",
    ]

    # Chart image
    if chart_path:
        chart_basename = Path(chart_path).name
        lines += [
            "## K-Line Chart",
            "",
            f"![{code} K-line]({chart_basename})",
            "",
        ]

    lines += [
        "## K-Line Snapshot",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 最新收盘 | ¥{last['close']:.2f} |",
        f"| 1日涨跌 | {pct_chg:+.2f}% ({abs_chg:+.2f}) |",
        f"| MA5 / MA20 / MA60 | ¥{last['ma5']:.2f} / ¥{last['ma20']:.2f} / ¥{last['ma60']:.2f} ({ma_stack}) |",
        f"| 布林带 Bollinger | Upper ¥{last['bb_upper']:.2f} · Mid ¥{last['bb_mid']:.2f} · Lower ¥{last['bb_lower']:.2f} (Width: {last['bb_width']:.1f}%) |",
        f"| ATR-14 (波动幅) | ¥{last['atr14']:.2f}/day ({last['atr_pct']:.1f}% of price) |",
        f"| 20日区间 | ¥{low20:.2f} – ¥{high20:.2f} |",
        f"| 成交量 vs 20日均 | {(vol_ratio-1)*100:+.0f}% ({vol_label}) |",
        "",
        "## Technical View — 技术面",
        "",
        f"- **趋势 Trend**: {ma_stack}",
        f"  - Weekly: {w_trend}",
        f"  - Monthly: {m_trend}",
        f"- **动量 Momentum**: 5D {_pct(r5)} | 10D {_pct(r10)} | 20D {_pct(r20)} | Ann.Vol {ann_vol:.1f}%",
        f"- **MACD**: {macd_desc}",
        f"  - Hist(last 5): `{[round(h,4) for h in hist_last5]}`",
        f"- **RSI-14**: {last['rsi14']:.1f} ({rsi_label})",
        f"- **BB Squeeze**: Width {last['bb_width']:.1f}% — {bb_desc}",
        f"- **支撑 Support**: ¥{support:.2f}",
        f"- **阻力 Resistance**: ¥{resistance:.2f}",
        f"- **ATR止损参考**: last close − 1.5×ATR = ¥{last['close']:.2f} − ¥{1.5*last['atr14']:.2f} ≈ **¥{trailing_stop:.2f}**",
        "",
    ]

    # Valuation
    lines += ["## Valuation — 估值", ""]
    if val.get("note"):
        lines.append(f"> {val['note']}")
        lines.append("")
    lines += [
        "| 指标 | 数值 |",
        "|---|---|",
    ]
    if val.get("pe_ttm") is not None:
        lines.append(f"| PE (TTM) | {val['pe_ttm']}x (EPS ¥{val.get('eps','N/A')}) |")
    else:
        lines.append("| PE (TTM) | N/A (EPS unavailable) |")
    if val.get("pb") is not None:
        lines.append(f"| PB | {val['pb']}x (BVPS ¥{val.get('book_value_per_share','N/A')}) |")
    lines += [
        f"| ROE | {val.get('roe','N/A')}% |",
        f"| 毛利率 | {val.get('gross_margin','N/A')}% |",
        f"| 营收 YoY | {_pct(val.get('revenue_yoy'))} |",
        f"| 净利 YoY | {_pct(val.get('net_profit_yoy'))} |",
        f"| 行业 | {val.get('industry','N/A')} |",
        f"| 最新公告 | {val.get('report_date','N/A')} |",
        "",
        "> 历史PE百分位不可用 — `stock_a_lg_indicator` 接口已下线",
        "",
    ]

    # Events
    lines += ["## Event Overlay — 事件", ""]
    for ev in event_lines:
        lines.append(ev if ev.startswith("- ") or ev.startswith("  ") else f"- {ev}")
    lines.append("")

    # Data freshness
    freshness_line = _fetch_meta_line(df_daily)
    if freshness_line:
        lines += ["## Data Freshness — 数据时效", "", freshness_line, ""]

    # Risk
    rsi_warn = "接近超买，注意回调" if last["rsi14"] > 65 else "中性区，无明显超买"
    lines += [
        "## Risk & Watchpoints — 风险",
        "",
        f"- **多单失效**: 若收盘跌破 MA20 (¥{last['ma20']:.2f}) + 放量 → 趋势走弱",
        f"- **布林下轨**: 跌破 BB Lower (¥{last['bb_lower']:.2f}) = 下行波动放大",
        f"- **RSI超买**: RSI {last['rsi14']:.1f} — {rsi_warn}",
        f"- **ATR止损**: 仓位管理参考 1 ATR = ¥{last['atr14']:.2f}",
        f"- **突破条件**: 重返 MA20 (¥{last['ma20']:.2f}) + MACD金叉 + 成交量 >+50% → 反转确认",
        "",
        "> ⚠ 本报告仅供信息参考，不构成任何投资建议。",
        "",
    ]

    # Execution sections
    if output_mode in {"full", "execution"}:
        plan = build_trade_plan(df_daily, df_weekly, df_monthly)
        al, ah = plan["aggressive_zone"]
        cl, ch = plan["confirm_zone"]
        bl, bh = plan["breakout_zone"]
        vol_r_pct = (vol_ratio - 1) * 100
        bias = "尾盘优先，早盘只适合小仓试错" if plan["close_preferred"] else "可早盘跟随，但仍需量价确认"
        bias_reason = "周/月级别尚未共振转强，尾盘更能确认是假反抽还是修复成立" if plan["close_preferred"] else "多周期偏强，早盘顺势参与的容错更高"
        lines += [
            "## Trading Plan — 交易执行版",
            "",
            "| 区间 | 价格 | 说明 |",
            "|---|---|---|",
            f"| 试错低吸区 | {_format_range(al, ah)} | 仅小仓 |",
            f"| 右侧确认区 | {_format_range(cl, ch)} | 站稳 MA20 后加仓 |",
            f"| 突破跟随区 | {_format_range(bl, bh)} | 放量突破阻力 |",
            f"| 试错止损 | ¥{plan['invalidation']:.2f} | |",
            f"| 结构止损 | ¥{plan['structural_stop']:.2f} | |",
            f"| 确认仓止损 | ¥{plan['confirm_stop']:.2f} | |",
            f"| 突破仓止损 | ¥{plan['breakout_stop']:.2f} | |",
            "",
            f"**观察主线**: 先看 ¥{plan['confirm_line']:.2f} 能否收回，再看 ¥{plan['breakout_line']:.2f} 能否放量突破",
            "",
            "## Watchlist — 三段式盯盘清单",
            "",
            f"| 阶段 | 内容 |",
            f"|---|---|",
            f"| 开盘前 | 写好试错区、确认线、失效线；默认不追第一笔。重点: {_format_range(al, ah)} / ¥{plan['confirm_line']:.2f} / ¥{plan['structural_stop']:.2f} |",
            f"| 盘中 | 回踩试错区止跌 → 小仓；站上 ¥{plan['confirm_line']:.2f} 且量能改善 → 加仓。量能 {vol_r_pct:+.0f}% vs 20日均 |",
            f"| 收盘前 | 收盘稳在 ¥{plan['confirm_line']:.2f} 上方 → 右侧修复成立；否则按反抽看待 |",
            "",
            "## Timing Bias — 早盘 vs 尾盘",
            "",
            f"| 项目 | 内容 |",
            f"|---|---|",
            f"| 执行偏好 | {bias} |",
            f"| 原因 | {bias_reason} |",
            f"| 早盘买条件 | 仅在 {_format_range(al, ah)} 一带止跌时小仓试错，不追高 |",
            f"| 尾盘买条件 | 收盘前稳定在 ¥{plan['confirm_line']:.2f} 上方，且回落不破 |",
            "",
        ]

    return "\n".join(lines)


def format_compare_markdown(symbol_reports: list[dict[str, Any]], output_mode: str = "structured") -> str:
    """Produce a Markdown version of the multi-stock comparison report."""
    ranked = build_relative_strength_data(symbol_reports)
    leader = ranked[0]
    laggard = ranked[-1]
    total = len(ranked)
    start_date = max(report["df_daily"]["date"].iloc[0] for report in symbol_reports)
    today = date.today()
    compared_symbols = " / ".join(f"{item['name']} ({item['code']})" for item in ranked)

    for item in ranked:
        item["priority"] = _priority_label(item["rank"], total)
    _assign_allocation_weights(ranked)

    priority_items = [item for item in ranked if item["priority"] == "右侧优先"]
    watch_items = [item for item in ranked if item["priority"] == "只配观察"]
    avoid_items = [item for item in ranked if item["priority"] == "应回避"]

    lines = _md_meta(f"Relative Strength — {compared_symbols}")
    lines += [
        f"# Relative Strength 对比报告",
        "",
        f"> 生成时间: {_ts_full()}  ",
        f"> 数据来源: AkShare · 前复权 qfq  ",
        "",
        "## Comparison Summary",
        "",
        "| 项目 | 内容 |",
        "|---|---|",
        f"| 对比标的 | {compared_symbols} |",
        f"| 分析区间 | {start_date} → {today} (日线 6M, qfq-adjusted) |",
        f"| Relative Leader | **{leader['name']} ({leader['code']})** |",
        f"| Relative Laggard | **{laggard['name']} ({laggard['code']})** |",
        "",
        "## Relative Strength",
        "",
        "| Symbol | 6M Return | Vol20D | Sharpe | RSI14 | ATR% | Rank | View | Weight |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for item in ranked:
        label = f"{item['name']} ({item['code']})"
        marker = " ← Leader" if item is leader else " ← Laggard" if item is laggard else ""
        lines.append(
            f"| **{label}** | {item['return_6m']:+.1f}% | {item['vol_20d']:.1f}% | "
            f"{item['sharpe_proxy']:.2f} | {item['rsi14']:.1f} | {item['atr_pct']:.1f}% | "
            f"{_ordinal(item['rank'])} | {item['priority']} | {item.get('suggested_weight', 0)}%{marker} |"
        )

    lines += [
        "",
        "## Execution Bias — 相对强弱执行结论",
        "",
        f"- **Leader 优先级**: {leader['name']} 更适合做右侧确认或突破跟随，因其 return / Sharpe / RSI 综合更强",
        f"- **Laggard 处理**: {laggard['name']} 只适合超跌反抽试错，若不能收回确认线则应降低优先级",
        "",
    ]

    if total >= 3:
        lines += [
            "## Priority Guidance — 统一优先级建议",
            "",
            "| 分类 | 标的 |",
            "|---|---|",
            f"| **右侧优先** | {_format_symbol_group(priority_items)} |",
            f"| **只配观察** | {_format_symbol_group(watch_items)} |",
            f"| **应回避** | {_format_symbol_group(avoid_items)} |",
            "",
            "## Portfolio Suggestion — 组合建议版",
            "",
            "| 分类 | 标的 | 建议权重 |",
            "|---|---|---|",
        ]
        for item in ranked:
            bucket = item["priority"]
            lines.append(f"| {bucket} | {item['name']} ({item['code']}) | {item.get('suggested_weight', 0)}% |")
        lines += [
            "",
            f"**主仓首选**: {leader['name']} ({leader['code']})",
            "",
            "> 权重说明: 相对强弱排序下的组合建议，不是精确仓位模型；默认主仓70% / 观察30% / 排除0% 框架。",
        ]
        if leader["return_6m"] < 0:
            lines.append(f"> ⚠ 即使相对最强标的仍为负收益，右侧优先仅代表相对占优，不代表趋势已确认。")
        lines.append("")

    # Cache Freshness
    freshness_rows = []
    for item in ranked:
        meta = item["report"]["df_daily"].attrs.get("fetch_meta") if hasattr(item["report"]["df_daily"], "attrs") else None
        if meta:
            src = "实时抓取" if meta.get("source") == "live" else "本地缓存回退"
            freshness_rows.append(
                f"| {item['name']} ({item['code']}) | {src} | {meta.get('last_bar_date','N/A')} | "
                f"{meta.get('cached_at','N/A')} | {meta.get('staleness_days','?')}天 |"
            )
    if freshness_rows:
        lines += [
            "## Cache Freshness — 缓存时效",
            "",
            "| 标的 | 来源 | 最近K线 | 缓存时间 | 距今 |",
            "|---|---|---|---|---|",
        ] + freshness_rows + [""]

    # Execution plans
    if output_mode in {"full", "execution"}:
        for tag, item in [("Leader Plan — 强者执行计划", leader), ("Laggard Plan — 弱者执行计划", laggard)]:
            plan = item["plan"]
            al, ah = plan["aggressive_zone"]
            cl, ch = plan["confirm_zone"]
            bl, bh = plan["breakout_zone"]
            bias = "尾盘确认优先" if plan["close_preferred"] else "可早盘跟随"
            lines += [
                f"## {tag}",
                "",
                f"**标的**: {item['name']} ({item['code']})",
                "",
                "| 区间 | 价格 |",
                "|---|---|",
                f"| 试错区 | {_format_range(al, ah)} |",
                f"| 确认区 | {_format_range(cl, ch)} |",
                f"| 突破区 | {_format_range(bl, bh)} |",
                f"| 试错止损 | ¥{plan['invalidation']:.2f} |",
                f"| 结构止损 | ¥{plan['structural_stop']:.2f} |",
                f"| 执行偏好 | {bias} |",
                "",
                f"**观察主线**: 先看 ¥{plan['confirm_line']:.2f}，再看 ¥{plan['breakout_line']:.2f}",
                "",
            ]

    lines += [
        "---",
        "",
        "> ⚠ 本报告仅供信息参考，不构成任何投资建议。",
        "",
    ]
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────

def run(raw_input: str | list[str], out_dir: str = ".", output_mode: str = "structured", output_format: str = "markdown") -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _ts()

    if isinstance(raw_input, str):
        symbols = [raw_input]
    else:
        symbols = raw_input

    if len(symbols) == 1:
        report_data = analyze_symbol(symbols[0], out_dir, output_mode=output_mode, render_chart=True)
        # Always print plain text to terminal
        print(report_data["report"])
        # Save plain text
        txt_path = out_dir / f"{report_data['code']}_analysis.txt"
        txt_path.write_text(report_data["report"], encoding="utf-8")
        print(f"[run] Report saved → {txt_path}")
        # Save markdown
        if output_format in {"markdown", "both"}:
            md_report = format_markdown(
                report_data["code"], report_data["name"], report_data["market_label"],
                report_data["df_daily"], report_data["df_weekly"], report_data["df_monthly"],
                report_data["val"], report_data["event_lines"],
                output_mode=output_mode,
                chart_path=report_data["chart_path"],
            )
            md_path = out_dir / f"{report_data['code']}_analysis_{ts}.md"
            md_path.write_text(md_report, encoding="utf-8")
            print(f"[run] Markdown saved → {md_path}")
        if report_data["chart_path"]:
            print(f"[run] Chart saved  → {report_data['chart_path']}")
        return

    symbol_reports = [
        analyze_symbol(symbol, out_dir, output_mode=output_mode, render_chart=False, include_context=False)
        for symbol in symbols
    ]
    # Plain text
    report = format_compare_output(symbol_reports, output_mode=output_mode)
    print(report)
    file_stub = "_vs_".join(r["code"] for r in symbol_reports)
    txt_path = out_dir / f"{file_stub}_relative_strength.txt"
    txt_path.write_text(report, encoding="utf-8")
    print(f"[run] Relative strength report saved → {txt_path}")
    # Markdown
    if output_format in {"markdown", "both"}:
        md_report = format_compare_markdown(symbol_reports, output_mode=output_mode)
        md_path = out_dir / f"{file_stub}_relative_strength_{ts}.md"
        md_path.write_text(md_report, encoding="utf-8")
        print(f"[run] Markdown saved → {md_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stock K-Line Analysis")
    parser.add_argument("symbols", nargs="*", help="One or more stock codes/names for analysis or relative-strength comparison")
    parser.add_argument("--out-dir", default=".", help="Directory for output files (default: current dir)")
    parser.add_argument(
        "--mode",
        choices=["structured", "full", "execution"],
        default="structured",
        help="Output style: structured analysis only, full analysis plus trading plan, or execution-focused report",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "both"],
        default="markdown",
        help="Output format: text only, markdown only (default), or both",
    )
    parser.add_argument(
        "--refresh-symbols",
        action="store_true",
        help="Fetch latest SH+SZ symbol list from exchanges and update data/a_share_symbols.csv, then exit",
    )
    args = parser.parse_args()
    if args.refresh_symbols:
        refresh_symbol_list()
        sys.exit(0)
    if not args.symbols:
        parser.error("Please provide at least one stock code or name.")
    run(args.symbols, out_dir=args.out_dir, output_mode=args.mode, output_format=args.format)

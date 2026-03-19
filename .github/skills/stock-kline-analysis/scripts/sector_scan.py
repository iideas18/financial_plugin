#!/usr/bin/env python3
"""
sector_scan.py — Livermore-style top-down sector scanner.

Identifies leading industry groups and concept themes by ranking
performance, fund flow, and surfacing leader stocks within each group.

Usage:
    python sector_scan.py                          # default: top 10 industry + concept
    python sector_scan.py --top 20                 # top 20
    python sector_scan.py --type industry          # industry only
    python sector_scan.py --type concept           # concept only
    python sector_scan.py --type fund-flow         # fund flow ranking
    python sector_scan.py --drill "小金属"          # drill into a specific board
    python sector_scan.py --format markdown        # markdown output
    python sector_scan.py --out-dir /tmp/reports   # custom output directory
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from proxy_config import apply_proxy
apply_proxy()  # configure proxy before any network calls

import akshare as ak
import pandas as pd

_CACHE_DIR = _SCRIPTS_DIR / ".cache"

# Retry config — mirrors fetch_kline.py pattern
_MAX_RETRIES = 3
_RETRY_DELAY = 1.5


# ────────────────────────────────────────────────────────────────────────────
# Cache helpers (same pattern as fetch_kline.py)
# ────────────────────────────────────────────────────────────────────────────

def _cache_path(kind: str) -> Path:
    return _CACHE_DIR / f"sector_{kind}_{datetime.now().strftime('%Y%m%d')}.csv"


def _read_cache(kind: str, max_age_minutes: int = 30) -> pd.DataFrame | None:
    p = _cache_path(kind)
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > max_age_minutes * 60:
        return None
    try:
        return pd.read_csv(p, dtype=str)
    except Exception:
        return None


def _write_cache(df: pd.DataFrame, kind: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_cache_path(kind), index=False, encoding="utf-8")


def _fetch_with_retry(fn, *args, label: str = "api", **kwargs) -> pd.DataFrame | None:
    """Call an akshare function with retries on network errors."""
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                print(f"[sector] Retry {label} ({attempt + 1}/{_MAX_RETRIES}): {e}", file=sys.stderr)
                time.sleep(_RETRY_DELAY * (attempt + 1))
            else:
                print(f"[sector] Failed {label} after {_MAX_RETRIES} attempts: {e}", file=sys.stderr)
    return None


# ────────────────────────────────────────────────────────────────────────────
# Data fetching — industry boards
# ────────────────────────────────────────────────────────────────────────────

def fetch_industry_boards(top_n: int = 10) -> list[dict[str, Any]]:
    """Fetch industry board ranking from East Money, sorted by daily %change."""
    cache_key = "industry_boards"
    cached = _read_cache(cache_key)
    if cached is not None:
        df = cached
        for col in ("涨跌幅", "总市值", "换手率"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        df = _fetch_with_retry(ak.stock_board_industry_name_em, label="industry_boards")
        if df is None:
            return []
        _write_cache(df, cache_key)

    # Sort by 涨跌幅 descending
    if "涨跌幅" not in df.columns:
        return []
    df = df.sort_values("涨跌幅", ascending=False).head(top_n)

    results = []
    for _, row in df.iterrows():
        results.append({
            "rank": int(row.get("排名", 0)) if pd.notna(row.get("排名")) else 0,
            "name": str(row.get("板块名称", "")),
            "code": str(row.get("板块代码", "")),
            "change_pct": float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else 0.0,
            "market_cap": float(row.get("总市值", 0)) if pd.notna(row.get("总市值")) else 0.0,
            "turnover": float(row.get("换手率", 0)) if pd.notna(row.get("换手率")) else 0.0,
            "rising": int(row.get("上涨家数", 0)) if pd.notna(row.get("上涨家数")) else 0,
            "falling": int(row.get("下跌家数", 0)) if pd.notna(row.get("下跌家数")) else 0,
            "leader": str(row.get("领涨股票", "")),
            "leader_change": float(row.get("领涨股票-涨跌幅", 0)) if pd.notna(row.get("领涨股票-涨跌幅")) else 0.0,
            "type": "industry",
        })
    return results


# ────────────────────────────────────────────────────────────────────────────
# Data fetching — concept boards
# ────────────────────────────────────────────────────────────────────────────

def fetch_concept_boards(top_n: int = 10) -> list[dict[str, Any]]:
    """Fetch concept/theme board ranking from East Money, sorted by daily %change."""
    cache_key = "concept_boards"
    cached = _read_cache(cache_key)
    if cached is not None:
        df = cached
        for col in ("涨跌幅", "总市值", "换手率"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        df = _fetch_with_retry(ak.stock_board_concept_name_em, label="concept_boards")
        if df is None:
            return []
        _write_cache(df, cache_key)

    if "涨跌幅" not in df.columns:
        return []
    df = df.sort_values("涨跌幅", ascending=False).head(top_n)

    results = []
    for _, row in df.iterrows():
        results.append({
            "rank": int(row.get("排名", 0)) if pd.notna(row.get("排名")) else 0,
            "name": str(row.get("板块名称", "")),
            "code": str(row.get("板块代码", "")),
            "change_pct": float(row["涨跌幅"]) if pd.notna(row["涨跌幅"]) else 0.0,
            "market_cap": float(row.get("总市值", 0)) if pd.notna(row.get("总市值")) else 0.0,
            "turnover": float(row.get("换手率", 0)) if pd.notna(row.get("换手率")) else 0.0,
            "rising": int(row.get("上涨家数", 0)) if pd.notna(row.get("上涨家数")) else 0,
            "falling": int(row.get("下跌家数", 0)) if pd.notna(row.get("下跌家数")) else 0,
            "leader": str(row.get("领涨股票", "")),
            "leader_change": float(row.get("领涨股票-涨跌幅", 0)) if pd.notna(row.get("领涨股票-涨跌幅")) else 0.0,
            "type": "concept",
        })
    return results


# ────────────────────────────────────────────────────────────────────────────
# Data fetching — sector fund flow ranking
# ────────────────────────────────────────────────────────────────────────────

def fetch_fund_flow(top_n: int = 10, period: str = "今日",
                    sector_type: str = "行业资金流") -> list[dict[str, Any]]:
    """Fetch sector fund flow ranking from East Money."""
    cache_key = f"fund_flow_{sector_type}_{period}".replace(" ", "_")
    cached = _read_cache(cache_key, max_age_minutes=30)
    if cached is not None:
        df = cached
        for col in df.columns:
            if "净" in col or "涨跌幅" in col:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        df = _fetch_with_retry(ak.stock_sector_fund_flow_rank,
                               indicator=period, sector_type=sector_type,
                               label=f"fund_flow_{sector_type}_{period}")
        if df is None:
            return []
        _write_cache(df, cache_key)

    df = df.head(top_n)

    results = []
    for _, row in df.iterrows():
        # Column names vary; try common patterns
        name = str(row.get("名称", row.get("板块名称", "")))
        change_pct = _safe_float(row.get("涨跌幅"))
        main_net = _safe_float(row.get("主力净流入-净额"))
        main_pct = _safe_float(row.get("主力净流入-净占比"))

        results.append({
            "rank": int(row.get("序号", 0)) if pd.notna(row.get("序号")) else 0,
            "name": name,
            "change_pct": change_pct,
            "main_net_inflow": main_net,
            "main_net_pct": main_pct,
            "type": "fund_flow",
            "sector_type": sector_type,
            "period": period,
        })
    return results


def _safe_float(val) -> float:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ────────────────────────────────────────────────────────────────────────────
# Drill into a board → constituent stocks
# ────────────────────────────────────────────────────────────────────────────

def fetch_board_constituents(board_name: str, board_type: str = "industry",
                             top_n: int = 10) -> list[dict[str, Any]]:
    """Fetch top constituent stocks of a given board, ranked by daily %change."""
    cache_key = f"cons_{board_type}_{board_name}"
    cached = _read_cache(cache_key, max_age_minutes=30)
    if cached is not None:
        df = cached
        for col in ("涨跌幅", "最新价", "市盈率-动态", "市净率"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        if board_type == "concept":
            df = _fetch_with_retry(ak.stock_board_concept_cons_em, symbol=board_name,
                                   label=f"cons_concept_{board_name}")
        else:
            df = _fetch_with_retry(ak.stock_board_industry_cons_em, symbol=board_name,
                                   label=f"cons_industry_{board_name}")
        if df is None:
            return []
        _write_cache(df, cache_key)

    if "涨跌幅" in df.columns:
        df = df.sort_values("涨跌幅", ascending=False)
    df = df.head(top_n)

    results = []
    for _, row in df.iterrows():
        results.append({
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": _safe_float(row.get("最新价")),
            "change_pct": _safe_float(row.get("涨跌幅")),
            "pe": _safe_float(row.get("市盈率-动态")),
            "pb": _safe_float(row.get("市净率")),
            "board_name": board_name,
            "board_type": board_type,
        })
    return results


# ────────────────────────────────────────────────────────────────────────────
# Full top-down scan: boards → leader stocks
# ────────────────────────────────────────────────────────────────────────────

def full_scan(top_boards: int = 10, top_stocks: int = 5,
              scan_type: str = "all") -> dict[str, Any]:
    """
    Run a Livermore-style top-down scan:
      1. Rank sectors/concepts by performance
      2. Check fund flow for confirmation
      3. Surface leader stocks in top boards

    Returns a dict with keys: industry, concept, fund_flow, leaders, timestamp
    """
    result: dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "industry": [],
        "concept": [],
        "fund_flow_industry": [],
        "fund_flow_concept": [],
        "leaders": [],
    }

    if scan_type in ("all", "industry"):
        result["industry"] = fetch_industry_boards(top_boards)

    if scan_type in ("all", "concept"):
        result["concept"] = fetch_concept_boards(top_boards)

    if scan_type in ("all", "fund-flow"):
        result["fund_flow_industry"] = fetch_fund_flow(top_boards, "今日", "行业资金流")
        result["fund_flow_concept"] = fetch_fund_flow(top_boards, "今日", "概念资金流")

    # Drill into top 3 boards for leader stocks
    if scan_type in ("all", "industry"):
        for board in result["industry"][:3]:
            constituents = fetch_board_constituents(board["name"], "industry", top_stocks)
            result["leaders"].append({
                "board_name": board["name"],
                "board_type": "industry",
                "board_change": board["change_pct"],
                "stocks": constituents,
            })

    if scan_type in ("all", "concept"):
        for board in result["concept"][:3]:
            constituents = fetch_board_constituents(board["name"], "concept", top_stocks)
            result["leaders"].append({
                "board_name": board["name"],
                "board_type": "concept",
                "board_change": board["change_pct"],
                "stocks": constituents,
            })

    return result


# ────────────────────────────────────────────────────────────────────────────
# Text formatter
# ────────────────────────────────────────────────────────────────────────────

def format_text(scan: dict[str, Any], drill: str | None = None) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("  SECTOR SCAN — Leading Groups (Livermore Style)")
    lines.append(f"  {scan['timestamp']}")
    lines.append("=" * 70)

    if scan.get("industry"):
        lines.append("")
        lines.append("[Industry Boards — 行业板块排名 (by daily %change)]")
        lines.append(f"  {'Rank':<5} {'Board':<14} {'Chg%':>7} {'Rise':>5} {'Fall':>5} {'Leader':<10} {'L.Chg%':>7}")
        lines.append("  " + "-" * 60)
        for b in scan["industry"]:
            lines.append(
                f"  {b['rank']:<5} {b['name']:<14} {b['change_pct']:>+6.2f}%"
                f" {b['rising']:>5} {b['falling']:>5}"
                f" {b['leader']:<10} {b['leader_change']:>+6.2f}%"
            )

    if scan.get("concept"):
        lines.append("")
        lines.append("[Concept Boards — 概念板块排名 (by daily %change)]")
        lines.append(f"  {'Rank':<5} {'Theme':<16} {'Chg%':>7} {'Rise':>5} {'Fall':>5} {'Leader':<10} {'L.Chg%':>7}")
        lines.append("  " + "-" * 62)
        for b in scan["concept"]:
            lines.append(
                f"  {b['rank']:<5} {b['name']:<16} {b['change_pct']:>+6.2f}%"
                f" {b['rising']:>5} {b['falling']:>5}"
                f" {b['leader']:<10} {b['leader_change']:>+6.2f}%"
            )

    if scan.get("fund_flow_industry"):
        lines.append("")
        lines.append("[Fund Flow — 行业资金流 (today)]")
        lines.append(f"  {'#':<4} {'Board':<14} {'Chg%':>7} {'Main Net':>14} {'Net%':>8}")
        lines.append("  " + "-" * 50)
        for f in scan["fund_flow_industry"]:
            net_str = _format_yuan(f["main_net_inflow"])
            lines.append(
                f"  {f['rank']:<4} {f['name']:<14} {f['change_pct']:>+6.2f}%"
                f" {net_str:>14} {f['main_net_pct']:>+7.2f}%"
            )

    if scan.get("fund_flow_concept"):
        lines.append("")
        lines.append("[Fund Flow — 概念资金流 (today)]")
        lines.append(f"  {'#':<4} {'Theme':<16} {'Chg%':>7} {'Main Net':>14} {'Net%':>8}")
        lines.append("  " + "-" * 52)
        for f in scan["fund_flow_concept"]:
            net_str = _format_yuan(f["main_net_inflow"])
            lines.append(
                f"  {f['rank']:<4} {f['name']:<16} {f['change_pct']:>+6.2f}%"
                f" {net_str:>14} {f['main_net_pct']:>+7.2f}%"
            )

    if scan.get("leaders"):
        lines.append("")
        lines.append("=" * 70)
        lines.append("  LEADER STOCKS — Top Stocks in Leading Groups")
        lines.append("=" * 70)
        for group in scan["leaders"]:
            tag = "行业" if group["board_type"] == "industry" else "概念"
            lines.append("")
            lines.append(f"  [{tag}] {group['board_name']} ({group['board_change']:+.2f}%)")
            lines.append(f"    {'Code':<8} {'Name':<10} {'Price':>8} {'Chg%':>7} {'PE':>7} {'PB':>6}")
            lines.append("    " + "-" * 48)
            for s in group["stocks"]:
                lines.append(
                    f"    {s['code']:<8} {s['name']:<10}"
                    f" {s['price']:>8.2f} {s['change_pct']:>+6.2f}%"
                    f" {s['pe']:>7.1f} {s['pb']:>6.2f}"
                )

    lines.append("")
    return "\n".join(lines)


def _format_yuan(val: float) -> str:
    """Format large yuan values to 亿/万."""
    abs_val = abs(val)
    if abs_val >= 1e8:
        return f"{val / 1e8:+.2f}亿"
    if abs_val >= 1e4:
        return f"{val / 1e4:+.1f}万"
    return f"{val:+.0f}"


# ────────────────────────────────────────────────────────────────────────────
# Markdown formatter
# ────────────────────────────────────────────────────────────────────────────

def format_markdown(scan: dict[str, Any]) -> str:
    lines = []
    lines.append("---")
    lines.append(f'title: "Sector Scan — Leading Groups"')
    lines.append(f"date: {scan['timestamp']}")
    lines.append("generator: sector-scan")
    lines.append("---")
    lines.append("")
    lines.append("# Sector Scan — Leading Groups 板块扫描")
    lines.append("")
    lines.append(f"> 生成时间: {scan['timestamp']}")
    lines.append("")

    if scan.get("industry"):
        lines.append("## Industry Boards — 行业板块排名")
        lines.append("")
        lines.append("| Rank | Board | Chg% | Rise | Fall | Leader | L.Chg% |")
        lines.append("|---:|---|---:|---:|---:|---|---:|")
        for b in scan["industry"]:
            lines.append(
                f"| {b['rank']} | **{b['name']}** | {b['change_pct']:+.2f}%"
                f" | {b['rising']} | {b['falling']}"
                f" | {b['leader']} | {b['leader_change']:+.2f}% |"
            )
        lines.append("")

    if scan.get("concept"):
        lines.append("## Concept Boards — 概念板块排名")
        lines.append("")
        lines.append("| Rank | Theme | Chg% | Rise | Fall | Leader | L.Chg% |")
        lines.append("|---:|---|---:|---:|---:|---|---:|")
        for b in scan["concept"]:
            lines.append(
                f"| {b['rank']} | **{b['name']}** | {b['change_pct']:+.2f}%"
                f" | {b['rising']} | {b['falling']}"
                f" | {b['leader']} | {b['leader_change']:+.2f}% |"
            )
        lines.append("")

    if scan.get("fund_flow_industry"):
        lines.append("## Fund Flow — 行业资金流 (today)")
        lines.append("")
        lines.append("| # | Board | Chg% | Main Net Inflow | Net% |")
        lines.append("|---:|---|---:|---:|---:|")
        for f in scan["fund_flow_industry"]:
            net_str = _format_yuan(f["main_net_inflow"])
            lines.append(
                f"| {f['rank']} | **{f['name']}** | {f['change_pct']:+.2f}%"
                f" | {net_str} | {f['main_net_pct']:+.2f}% |"
            )
        lines.append("")

    if scan.get("fund_flow_concept"):
        lines.append("## Fund Flow — 概念资金流 (today)")
        lines.append("")
        lines.append("| # | Theme | Chg% | Main Net Inflow | Net% |")
        lines.append("|---:|---|---:|---:|---:|")
        for f in scan["fund_flow_concept"]:
            net_str = _format_yuan(f["main_net_inflow"])
            lines.append(
                f"| {f['rank']} | **{f['name']}** | {f['change_pct']:+.2f}%"
                f" | {net_str} | {f['main_net_pct']:+.2f}% |"
            )
        lines.append("")

    if scan.get("leaders"):
        lines.append("## Leader Stocks — 龙头个股")
        lines.append("")
        for group in scan["leaders"]:
            tag = "行业" if group["board_type"] == "industry" else "概念"
            lines.append(f"### [{tag}] {group['board_name']} ({group['board_change']:+.2f}%)")
            lines.append("")
            lines.append("| Code | Name | Price | Chg% | PE | PB |")
            lines.append("|---|---|---:|---:|---:|---:|")
            for s in group["stocks"]:
                lines.append(
                    f"| {s['code']} | **{s['name']}** | ¥{s['price']:.2f}"
                    f" | {s['change_pct']:+.2f}% | {s['pe']:.1f} | {s['pb']:.2f} |"
                )
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> *\"Trade the leaders, leave the laggards alone.\"* — Jesse Livermore")
    lines.append("")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# JSON output (for web UI)
# ────────────────────────────────────────────────────────────────────────────

def to_json(scan: dict[str, Any]) -> str:
    return json.dumps(scan, ensure_ascii=False, indent=2)


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sector Scan — Leading Groups (Livermore Style)")
    parser.add_argument("--top", type=int, default=10, help="Number of top boards to show (default: 10)")
    parser.add_argument("--top-stocks", type=int, default=5, help="Number of leader stocks per board (default: 5)")
    parser.add_argument("--type", choices=["all", "industry", "concept", "fund-flow"],
                        default="all", help="Scan type (default: all)")
    parser.add_argument("--drill", type=str, default=None,
                        help="Drill into a specific board name for constituent stocks")
    parser.add_argument("--drill-type", choices=["industry", "concept"], default="industry",
                        help="Type of board to drill into (default: industry)")
    parser.add_argument("--format", choices=["text", "markdown", "json", "both"],
                        default="text", help="Output format (default: text)")
    parser.add_argument("--out-dir", default=".", help="Directory for output files")
    parser.add_argument("--proxy", type=str, default=None,
                        help="Proxy URL (e.g. http://proxy:912). Overrides saved config.")
    args = parser.parse_args()

    if args.proxy:
        apply_proxy(args.proxy)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # Drill mode: show constituents of a specific board
    if args.drill:
        constituents = fetch_board_constituents(args.drill, args.drill_type, args.top)
        if not constituents:
            print(f"No data found for board '{args.drill}'", file=sys.stderr)
            sys.exit(1)
        scan = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "industry": [], "concept": [],
            "fund_flow_industry": [], "fund_flow_concept": [],
            "leaders": [{
                "board_name": args.drill,
                "board_type": args.drill_type,
                "board_change": 0.0,
                "stocks": constituents,
            }],
        }
    else:
        scan = full_scan(top_boards=args.top, top_stocks=args.top_stocks, scan_type=args.type)

    # Output
    text_report = format_text(scan)
    print(text_report)

    if args.format in ("text", "both"):
        txt_path = out_dir / f"sector_scan_{ts}.txt"
        txt_path.write_text(text_report, encoding="utf-8")
        print(f"[scan] Text saved → {txt_path}")

    if args.format in ("markdown", "both"):
        md_report = format_markdown(scan)
        md_path = out_dir / f"sector_scan_{ts}.md"
        md_path.write_text(md_report, encoding="utf-8")
        print(f"[scan] Markdown saved → {md_path}")

    if args.format == "json":
        json_str = to_json(scan)
        json_path = out_dir / f"sector_scan_{ts}.json"
        json_path.write_text(json_str, encoding="utf-8")
        print(f"[scan] JSON saved → {json_path}")


if __name__ == "__main__":
    main()

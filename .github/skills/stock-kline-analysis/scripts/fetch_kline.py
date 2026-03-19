"""
fetch_kline.py — Step 2: Fetch multi-timeframe K-line data for a given A-share symbol.

Usage:
    from fetch_kline import fetch_all_timeframes
    df_daily, df_weekly, df_monthly = fetch_all_timeframes("000063")
"""

import akshare as ak
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
import time
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from proxy_config import apply_proxy
apply_proxy()  # configure proxy before any network calls


# ── Column name map ─────────────────────────────────────────────────────────
# stock_zh_a_hist returns 12 Chinese-named columns; we keep only these 6.
_COL_MAP = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
}

_CACHE_DIR = Path(__file__).resolve().parent / ".cache"


def _cache_path(code: str, period: str, adjust: str) -> Path:
    safe_adjust = adjust or "none"
    return _CACHE_DIR / f"{code}_{period}_{safe_adjust}.csv"


def _save_cache(df: pd.DataFrame, code: str, period: str, adjust: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_cache_path(code, period, adjust), index=False, encoding="utf-8")


def _attach_fetch_meta(df: pd.DataFrame, source: str, cache_file: Path, period: str) -> pd.DataFrame:
    last_bar = pd.to_datetime(df["date"].iloc[-1]).date()
    cached_at = datetime.fromtimestamp(cache_file.stat().st_mtime)
    df.attrs["fetch_meta"] = {
        "source": source,
        "period": period,
        "cache_file": cache_file.name,
        "cached_at": cached_at.strftime("%Y-%m-%d %H:%M:%S"),
        "last_bar_date": last_bar.isoformat(),
        "staleness_days": (date.today() - last_bar).days,
    }
    return df


def _load_cache(
    code: str,
    period: str,
    adjust: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame | None:
    cache_file = _cache_path(code, period, adjust)
    if not cache_file.exists():
        return None

    try:
        df = pd.read_csv(cache_file)
        df["date"] = pd.to_datetime(df["date"])
        window = df[
            (df["date"] >= pd.to_datetime(start_date, format="%Y%m%d"))
            & (df["date"] <= pd.to_datetime(end_date, format="%Y%m%d"))
        ].copy()
        if window.empty:
            return None
        window["date"] = window["date"].dt.strftime("%Y-%m-%d")
        print(f"[fetch_kline] Using cached {period} data for {code} from {cache_file.name}")
        window = window.reset_index(drop=True)
        return _attach_fetch_meta(window, source="cache", cache_file=cache_file, period=period)
    except Exception as e:
        print(f"[fetch_kline] Failed to read cache {cache_file.name}: {e}")
        return None


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Chinese columns and return a clean 6-column OHLCV frame."""
    df = df.rename(columns=_COL_MAP)
    df = (
        df[["date", "open", "high", "low", "close", "volume"]]
        .sort_values("date")
        .drop_duplicates("date")
        .reset_index(drop=True)
    )
    # Ensure date is always a consistent string type to avoid str vs datetime.date mix
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def fetch_timeframe(
    code: str,
    period: str,
    start_date: str,
    end_date: str,
    adjust: str = "qfq",
) -> pd.DataFrame | None:
    """
    Fetch one timeframe with a single retry on network error.
    Returns None (and prints a warning) if the frame comes back empty or fails.
    """
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period=period,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
            df = normalize(df)
            if df.empty:
                print(f"[fetch_kline] WARNING: {period} frame empty for {code} "
                      f"(suspended / delisted / holiday?)")
                return _load_cache(code, period, adjust, start_date, end_date)
            _save_cache(df, code, period, adjust)
            return _attach_fetch_meta(df, source="live", cache_file=_cache_path(code, period, adjust), period=period)
        except Exception as e:
            if attempt < 2:
                print(f"[fetch_kline] Retry {period} after error: {e}")
                time.sleep(1.2 * (attempt + 1))
            else:
                print(f"[fetch_kline] FAILED {period} for {code}: {e}")
                return _load_cache(code, period, adjust, start_date, end_date)


def fetch_all_timeframes(
    code: str,
    adjust: str = "qfq",
) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    """
    Fetch daily (6M), weekly (1Y), and monthly (3Y) K-line data.

    Returns
    -------
    df_daily   : required; raises RuntimeError if empty.
    df_weekly  : may be None if fetch fails.
    df_monthly : may be None if fetch fails.
    """
    today = date.today()
    end = today.strftime("%Y%m%d")

    df_daily = fetch_timeframe(
        code, "daily",
        start_date=(today - timedelta(days=182)).strftime("%Y%m%d"),
        end_date=end,
        adjust=adjust,
    )
    if df_daily is None or len(df_daily) < 20:
        raise RuntimeError(
            f"Daily K-line for {code} returned < 20 bars — "
            "check symbol, market suspension, or date range."
        )

    df_weekly = fetch_timeframe(
        code, "weekly",
        start_date=(today - timedelta(days=365)).strftime("%Y%m%d"),
        end_date=end,
        adjust=adjust,
    )

    df_monthly = fetch_timeframe(
        code, "monthly",
        start_date=(today - timedelta(days=365 * 3)).strftime("%Y%m%d"),
        end_date=end,
        adjust=adjust,
    )

    return df_daily, df_weekly, df_monthly


# ── Quick smoke-test ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    symbol = sys.argv[1] if len(sys.argv) > 1 else "000063"
    d, w, m = fetch_all_timeframes(symbol)
    print(f"Daily  : {len(d):>4} rows  last={d['date'].iloc[-1]}")
    print(f"Weekly : {len(w):>4} rows  last={w['date'].iloc[-1]}" if w is not None else "Weekly : FAILED")
    print(f"Monthly: {len(m):>4} rows  last={m['date'].iloc[-1]}" if m is not None else "Monthly: FAILED")
    print(d.tail(3).to_string(index=False))

"""
Classic floor-trader pivot points, computed from the PRIOR period's OHLC and
attached onto an intraday/daily OHLC dataframe by calendar date.

Support levels: S1, S2, S3   |   Resistance levels: R1, R2, R3   |   Pivot: PP
"""

from __future__ import annotations

import pandas as pd

SUPPORT_KEYS = ["S1", "S2", "S3"]
RESISTANCE_KEYS = ["R1", "R2", "R3"]
ALL_LEVEL_KEYS = ["PP", "R1", "R2", "R3", "S1", "S2", "S3"]


def calculate_pivot_points(high: float, low: float, close: float) -> dict:
    pp = (high + low + close) / 3.0
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    return {"PP": pp, "R1": r1, "S1": s1, "R2": r2, "S2": s2, "R3": r3, "S3": s3}


def _period_ohlc(daily_df: pd.DataFrame, basis: str) -> pd.DataFrame:
    """Aggregate the daily dataframe into the pivot basis period (Weekly/Monthly),
    returning one row per period with high/low/close of that period."""
    d = daily_df.copy()
    d = d.set_index("timestamp")
    if basis == "Weekly":
        rule = "W-FRI"
    elif basis == "Monthly":
        rule = "ME"
    else:
        raise ValueError(basis)

    agg = d.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    agg = agg.reset_index()
    return agg


def build_pivot_table(daily_df: pd.DataFrame, basis: str = "Daily") -> pd.DataFrame:
    """Build a per-calendar-date table of pivot levels, where each date's levels are
    computed from the PRIOR completed period's OHLC (previous day / week / month).

    Returns a DataFrame with columns: date, PP, R1, R2, R3, S1, S2, S3
    """
    if daily_df.empty:
        return pd.DataFrame(columns=["date"] + ALL_LEVEL_KEYS)

    daily_df = daily_df.copy()
    daily_df["date"] = daily_df["timestamp"].dt.date

    if basis == "Daily":
        prev = daily_df[["high", "low", "close"]].shift(1)
        rows = []
        for i, row in daily_df.iterrows():
            if prev.loc[i].isna().any():
                rows.append({"date": row["date"], **{k: None for k in ALL_LEVEL_KEYS}})
            else:
                levels = calculate_pivot_points(prev.loc[i, "high"], prev.loc[i, "low"], prev.loc[i, "close"])
                rows.append({"date": row["date"], **levels})
        return pd.DataFrame(rows)

    # Weekly / Monthly: compute one set of levels per period (from the PRIOR period),
    # then broadcast that to every calendar date falling inside the following period.
    periods = _period_ohlc(daily_df, basis)
    periods = periods.sort_values("timestamp").reset_index(drop=True)
    periods["period_end"] = periods["timestamp"]

    # shift OHLC by one period so period N's levels come from period N-1
    periods["lvl_high"] = periods["high"].shift(1)
    periods["lvl_low"] = periods["low"].shift(1)
    periods["lvl_close"] = periods["close"].shift(1)

    rows = []
    for i, row in daily_df.iterrows():
        ts = row["timestamp"]
        # find the period this date belongs to: first period_end >= ts
        match = periods[periods["period_end"] >= ts]
        if match.empty or match.iloc[0][["lvl_high", "lvl_low", "lvl_close"]].isna().any():
            rows.append({"date": row["date"], **{k: None for k in ALL_LEVEL_KEYS}})
            continue
        m = match.iloc[0]
        levels = calculate_pivot_points(m["lvl_high"], m["lvl_low"], m["lvl_close"])
        rows.append({"date": row["date"], **levels})

    return pd.DataFrame(rows)


def attach_pivots(df: pd.DataFrame, pivot_table: pd.DataFrame) -> pd.DataFrame:
    """Left-merge pivot levels onto an OHLC dataframe by calendar date."""
    out = df.copy()
    out["date"] = out["timestamp"].dt.date
    out = out.merge(pivot_table, on="date", how="left")
    return out


def nearest_level(price: float, levels: dict, keys: list[str], tolerance_pct: float):
    """Return (level_name, level_value) for the closest matching level within tolerance,
    or (None, None) if nothing is within tolerance."""
    best = None
    for k in keys:
        v = levels.get(k)
        if v is None or pd.isna(v):
            continue
        dist_pct = abs(price - v) / v * 100.0
        if dist_pct <= tolerance_pct:
            if best is None or dist_pct < best[2]:
                best = (k, v, dist_pct)
    if best is None:
        return None, None
    return best[0], best[1]

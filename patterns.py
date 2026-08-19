"""
Bullish / Bearish Abandoned Baby detection.

Bullish Abandoned Baby
  Day1: long red/black candle
  Day2: doji that gaps FULLY below Day1's low  (day2.high < day1.low)
  Day3: long green/white candle that gaps FULLY above Day2's high (day3.low > day2.high)
        AND closes above Day1's OPEN

Bearish Abandoned Baby (mirror)
  Day1: long green/white candle
  Day2: doji that gaps FULLY above Day1's high (day2.low > day1.high)
  Day3: long red/black candle that gaps FULLY below Day2's low (day3.high < day2.low)
        AND closes below Day1's OPEN

Both patterns are only reported as valid signals when Day2 (the doji / reversal point)
sits at or very near a pivot support level (bullish) or pivot resistance level (bearish).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import pivots as pv


@dataclass
class PatternMatch:
    symbol: str
    pattern: str  # "Bullish Abandoned Baby" | "Bearish Abandoned Baby"
    day1_time: pd.Timestamp
    day2_time: pd.Timestamp
    day3_time: pd.Timestamp
    day1: dict
    day2: dict
    day3: dict
    level_name: str
    level_value: float
    distance_pct: float


def _body(row) -> float:
    return abs(row["close"] - row["open"])


def _range(row) -> float:
    return row["high"] - row["low"]


def _is_long_body(row, body_ratio_threshold: float) -> bool:
    rng = _range(row)
    if rng <= 0:
        return False
    return (_body(row) / rng) >= body_ratio_threshold


def _is_doji(row, doji_ratio_threshold: float) -> bool:
    rng = _range(row)
    if rng <= 0:
        return True
    return (_body(row) / rng) <= doji_ratio_threshold


def detect_patterns(
    df: pd.DataFrame,
    symbol: str,
    pattern_type: str,
    body_ratio_threshold: float = 0.55,
    doji_ratio_threshold: float = 0.12,
    tolerance_pct: float = 0.5,
) -> list[PatternMatch]:
    """
    df must already have pivot columns attached (PP, R1..R3, S1..S3) via pivots.attach_pivots.
    pattern_type: "Bullish", "Bearish", or "Both"
    """
    matches: list[PatternMatch] = []
    if df is None or len(df) < 3:
        return matches

    want_bull = pattern_type in ("Bullish", "Both")
    want_bear = pattern_type in ("Bearish", "Both")

    for i in range(2, len(df)):
        day1 = df.iloc[i - 2]
        day2 = df.iloc[i - 1]
        day3 = df.iloc[i]

        if want_bull:
            cond_day1_red = day1["close"] < day1["open"]
            long1 = _is_long_body(day1, body_ratio_threshold)
            doji2 = _is_doji(day2, doji_ratio_threshold)
            gap_down = day2["high"] < day1["low"]
            cond_day3_green = day3["close"] > day3["open"]
            long3 = _is_long_body(day3, body_ratio_threshold)
            gap_up = day3["low"] > day2["high"]
            closes_above_open1 = day3["close"] > day1["open"]

            if (
                cond_day1_red
                and long1
                and doji2
                and gap_down
                and cond_day3_green
                and long3
                and gap_up
                and closes_above_open1
            ):
                levels = {k: day2.get(k) for k in pv.ALL_LEVEL_KEYS}
                level_name, level_value = pv.nearest_level(
                    day2["low"], levels, pv.SUPPORT_KEYS + ["PP"], tolerance_pct
                )
                if level_name is not None:
                    dist_pct = abs(day2["low"] - level_value) / level_value * 100.0
                    matches.append(
                        PatternMatch(
                            symbol=symbol,
                            pattern="Bullish Abandoned Baby",
                            day1_time=day1["timestamp"],
                            day2_time=day2["timestamp"],
                            day3_time=day3["timestamp"],
                            day1=day1.to_dict(),
                            day2=day2.to_dict(),
                            day3=day3.to_dict(),
                            level_name=level_name,
                            level_value=level_value,
                            distance_pct=dist_pct,
                        )
                    )

        if want_bear:
            cond_day1_green = day1["close"] > day1["open"]
            long1 = _is_long_body(day1, body_ratio_threshold)
            doji2 = _is_doji(day2, doji_ratio_threshold)
            gap_up = day2["low"] > day1["high"]
            cond_day3_red = day3["close"] < day3["open"]
            long3 = _is_long_body(day3, body_ratio_threshold)
            gap_down = day3["high"] < day2["low"]
            closes_below_open1 = day3["close"] < day1["open"]

            if (
                cond_day1_green
                and long1
                and doji2
                and gap_up
                and cond_day3_red
                and long3
                and gap_down
                and closes_below_open1
            ):
                levels = {k: day2.get(k) for k in pv.ALL_LEVEL_KEYS}
                level_name, level_value = pv.nearest_level(
                    day2["high"], levels, pv.RESISTANCE_KEYS + ["PP"], tolerance_pct
                )
                if level_name is not None:
                    dist_pct = abs(day2["high"] - level_value) / level_value * 100.0
                    matches.append(
                        PatternMatch(
                            symbol=symbol,
                            pattern="Bearish Abandoned Baby",
                            day1_time=day1["timestamp"],
                            day2_time=day2["timestamp"],
                            day3_time=day3["timestamp"],
                            day1=day1.to_dict(),
                            day2=day2.to_dict(),
                            day3=day3.to_dict(),
                            level_name=level_name,
                            level_value=level_value,
                            distance_pct=dist_pct,
                        )
                    )

    return matches

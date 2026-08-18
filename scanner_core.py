"""
scanner_core.py -- shared, tested detection engine for the Abandoned Baby scanners.

Both the CLI/Tkinter tool (abandoned_baby_scanner.py) and the Streamlit web
app (streamlit_app.py) import from this file, so the pattern logic lives in
exactly one place.

BULLISH ABANDONED BABY:
    Day 1 : Long BLACK/RED candle   (bearish, body clearly bigger than average)
    Day 2 : DOJI that GAPS DOWN     (entirely below Day-1's low -> island down)
    Day 3 : Long WHITE/GREEN candle that GAPS UP from the doji (entirely above
            Day-2's high) AND whose CLOSE finishes ABOVE the top of Day-1's
            red body (close3 > open1).

BEARISH ABANDONED BABY (mirror image):
    Day 1 : Long WHITE/GREEN candle (bullish, body clearly bigger than average)
    Day 2 : DOJI that GAPS UP       (entirely above Day-1's high -> island up)
    Day 3 : Long BLACK/RED candle that GAPS DOWN from the doji (entirely below
            Day-2's low) AND whose CLOSE finishes BELOW the bottom of Day-1's
            green body (close3 < open1).

EMA filter:
    Bullish: doji forms at/just below the EMA (support test), Day 3 closes back above it.
    Bearish: doji forms at/just above the EMA (resistance test), Day 3 closes back below it.
"""

import time
import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None


# --------------------------------------------------------------------------
# Core pattern logic (pure pandas, no external candlestick lib needed)
# --------------------------------------------------------------------------

def add_indicators(df: pd.DataFrame, ema_length: int = 200) -> pd.DataFrame:
    df = df.copy()
    df["EMA"] = df["Close"].ewm(span=ema_length, adjust=False).mean()
    df["Body"] = (df["Close"] - df["Open"]).abs()
    df["Range"] = (df["High"] - df["Low"]).replace(0, np.nan)
    df["BodyPct"] = df["Body"] / df["Range"]
    # rolling average body size (excluding the current bar) used to judge
    # whether a candle is "long" relative to recent action
    df["AvgBody20"] = df["Body"].rolling(20).mean().shift(1)
    return df


def find_bullish_abandoned_baby(
    df: pd.DataFrame,
    doji_body_pct: float = 0.10,      # doji body must be <= 10% of its range
    long_body_mult: float = 1.0,      # day1/day3 body must be >= 1.0x avg body
    ema_tolerance_pct: float = 0.03,  # doji must be within 3% of EMA200
    strict_gap: bool = True,          # require full-range island gaps
):
    """
    Scans a single ticker's OHLC dataframe (with Date/Open/High/Low/Close and
    EMA200/Body/Range/BodyPct/AvgBody20 columns already added) and returns a
    list of dicts, one per detected pattern, with the date of Day 3
    (confirmation day) and supporting details.
    """
    hits = []
    n = len(df)

    for i in range(2, n):
        d1 = df.iloc[i - 2]   # first day: long red
        d2 = df.iloc[i - 1]   # second day: doji, gapped down
        d3 = df.iloc[i]       # third day: long green, confirmation

        if pd.isna(d1["AvgBody20"]) or d1["AvgBody20"] == 0:
            continue
        if pd.isna(d1["Range"]) or pd.isna(d2["Range"]) or pd.isna(d3["Range"]):
            continue

        # ---- Day 1: long bearish (red) candle -----------------------------
        d1_bearish = d1["Close"] < d1["Open"]
        d1_long = d1["Body"] >= long_body_mult * d1["AvgBody20"]

        # ---- Day 2: doji -----------------------------------------------
        d2_is_doji = (not pd.isna(d2["BodyPct"])) and d2["BodyPct"] <= doji_body_pct

        # ---- Day 3: long bullish (green) candle --------------------------
        d3_bullish = d3["Close"] > d3["Open"]
        d3_long = d3["Body"] >= long_body_mult * d1["AvgBody20"]

        # ---- Gaps (island pattern) --------------------------------------
        if strict_gap:
            gap_down = d2["High"] < d1["Low"]        # day2 entirely below day1
            gap_up = d3["Low"] > d2["High"]           # day3 entirely above day2
        else:
            gap_down = max(d2["Open"], d2["Close"]) < d1["Low"]
            gap_up = min(d3["Open"], d3["Close"]) > d2["High"]

        # ---- Confirmation: green candle closes ABOVE the red candle -----
        closes_above_red = d3["Close"] > d1["Open"]

        if not (d1_bearish and d1_long and d2_is_doji and d3_bullish and d3_long
                and gap_down and gap_up and closes_above_red):
            continue

        # ---- EMA filter: pattern must form at/near the chosen EMA ------
        ema_at_doji = d2["EMA"]
        if pd.isna(ema_at_doji):
            continue
        # doji (and ideally day1's low too) should sit at-or-below the EMA,
        # within the given tolerance, i.e. price was testing the EMA
        near_ema = (d2["Low"] <= ema_at_doji * (1 + ema_tolerance_pct)) and \
                   (d2["Low"] >= ema_at_doji * (1 - 3 * ema_tolerance_pct))
        reclaims_ema = d3["Close"] >= ema_at_doji

        if not (near_ema and reclaims_ema):
            continue

        hits.append({
            "day1_date": d1.name, "day2_date": d2.name, "day3_date": d3.name,
            "day1_open": round(d1["Open"], 2), "day1_close": round(d1["Close"], 2),
            "day2_doji_close": round(d2["Close"], 2),
            "day3_close": round(d3["Close"], 2),
            "ema_at_doji": round(ema_at_doji, 2),
        })

    return hits


def find_bearish_abandoned_baby(
    df: pd.DataFrame,
    doji_body_pct: float = 0.10,      # doji body must be <= 10% of its range
    long_body_mult: float = 1.0,      # day1/day3 body must be >= 1.0x avg body
    ema_tolerance_pct: float = 0.03,  # doji must be within 3% of EMA
    strict_gap: bool = True,          # require full-range island gaps
):
    """
    Mirror image of find_bullish_abandoned_baby, matching the textbook
    Bearish Abandoned Baby:

        Day 1 : Long WHITE/GREEN candle (bullish, body clearly bigger than average)
        Day 2 : DOJI that GAPS UP        (entirely above Day-1's high -> an
                                           island on the upside)
        Day 3 : Long BLACK/RED candle that GAPS DOWN from the doji (entirely
                below Day-2's low -> an island on the downside) AND whose
                CLOSE finishes BELOW the bottom of Day-1's green body
                (i.e. close3 < open1) -- the red candle must close below the
                white candle.

    EMA filter: the doji must form at/just above the EMA (a failed test of
    resistance) and Day 3 must close back below it.
    """
    hits = []
    n = len(df)

    for i in range(2, n):
        d1 = df.iloc[i - 2]   # first day: long white/green
        d2 = df.iloc[i - 1]   # second day: doji, gapped up
        d3 = df.iloc[i]       # third day: long black/red, confirmation

        if pd.isna(d1["AvgBody20"]) or d1["AvgBody20"] == 0:
            continue
        if pd.isna(d1["Range"]) or pd.isna(d2["Range"]) or pd.isna(d3["Range"]):
            continue

        # ---- Day 1: long bullish (white/green) candle --------------------
        d1_bullish = d1["Close"] > d1["Open"]
        d1_long = d1["Body"] >= long_body_mult * d1["AvgBody20"]

        # ---- Day 2: doji -----------------------------------------------
        d2_is_doji = (not pd.isna(d2["BodyPct"])) and d2["BodyPct"] <= doji_body_pct

        # ---- Day 3: long bearish (black/red) candle -----------------------
        d3_bearish = d3["Close"] < d3["Open"]
        d3_long = d3["Body"] >= long_body_mult * d1["AvgBody20"]

        # ---- Gaps (island pattern) --------------------------------------
        if strict_gap:
            gap_up = d2["Low"] > d1["High"]           # day2 entirely above day1
            gap_down = d3["High"] < d2["Low"]          # day3 entirely below day2
        else:
            gap_up = min(d2["Open"], d2["Close"]) > d1["High"]
            gap_down = max(d3["Open"], d3["Close"]) < d2["Low"]

        # ---- Confirmation: red candle closes BELOW the white candle -----
        closes_below_white = d3["Close"] < d1["Open"]

        if not (d1_bullish and d1_long and d2_is_doji and d3_bearish and d3_long
                and gap_up and gap_down and closes_below_white):
            continue

        # ---- EMA filter: pattern must form at/near the chosen EMA -------
        ema_at_doji = d2["EMA"]
        if pd.isna(ema_at_doji):
            continue
        # doji should sit at-or-above the EMA, within tolerance, i.e. price
        # was testing the EMA as resistance from below
        near_ema = (d2["High"] >= ema_at_doji * (1 - ema_tolerance_pct)) and \
                   (d2["High"] <= ema_at_doji * (1 + 3 * ema_tolerance_pct))
        breaks_ema = d3["Close"] <= ema_at_doji

        if not (near_ema and breaks_ema):
            continue

        hits.append({
            "day1_date": d1.name, "day2_date": d2.name, "day3_date": d3.name,
            "day1_open": round(d1["Open"], 2), "day1_close": round(d1["Close"], 2),
            "day2_doji_close": round(d2["Close"], 2),
            "day3_close": round(d3["Close"], 2),
            "ema_at_doji": round(ema_at_doji, 2),
        })

    return hits


# --------------------------------------------------------------------------
# Data fetching + scanning across a ticker list
# --------------------------------------------------------------------------

PATTERN_FUNCS = {
    "bullish": find_bullish_abandoned_baby,
    "bearish": find_bearish_abandoned_baby,
}


def fetch_ohlc(ticker: str, period: str = "3y", interval: str = "1d") -> pd.DataFrame:
    """
    interval: any yfinance-supported bar size, e.g.
        '1d'  = daily   '1wk' = weekly   '1mo' = monthly
        '1h','30m','15m','5m' = intraday (yfinance limits how far back
        intraday data goes -- typically 60 days for anything below 1h,
        and ~730 days for 1h -- so use a shorter --period with these)
    """
    if yf is None:
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance")
    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df


def scan_tickers(tickers, period="3y", interval="1d", ema_length=200, pattern="both", **pattern_kwargs):
    """
    pattern: "bullish", "bearish", or "both" -- this is the switch that
    controls which pattern(s) get scanned for.
    """
    results = {}
    funcs = PATTERN_FUNCS if pattern == "both" else {pattern: PATTERN_FUNCS[pattern]}

    for t in tickers:
        try:
            df = fetch_ohlc(t, period=period, interval=interval)
            if df.empty or len(df) < ema_length + 10:
                print(f"[skip] {t}: not enough data for a {ema_length}-period EMA "
                      f"on this timeframe (got {len(df)} bars)")
                continue
            df = add_indicators(df, ema_length=ema_length)

            all_hits = []
            for label, fn in funcs.items():
                hits = fn(df, **pattern_kwargs)
                for h in hits:
                    h["pattern"] = label
                all_hits.extend(hits)
            all_hits.sort(key=lambda h: h["day3_date"])

            if all_hits:
                results[t] = all_hits
                print(f"[MATCH] {t}: {len(all_hits)} pattern(s) found, most recent "
                      f"{all_hits[-1]['pattern']} on {all_hits[-1]['day3_date'].date()}")
            else:
                print(f"[none ] {t}")
        except Exception as e:
            print(f"[error] {t}: {e}")
        time.sleep(0.3)  # be polite to the data source
    return results

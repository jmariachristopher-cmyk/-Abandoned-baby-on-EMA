
import streamlit as st
import pandas as pd
import numpy as np
from angelone_client import AngelOneClient

st.set_page_config(page_title="Abandoned Baby S/R Scanner", page_icon="🔎", layout="wide")

# ============================================================
# INDICATORS
# ============================================================
def prepare(df, ema_len):
    x = df.copy().sort_values("date").reset_index(drop=True)
    x["ema"] = x["close"].ewm(span=int(ema_len), adjust=False).mean()
    x["body"] = (x["close"] - x["open"]).abs()
    x["range"] = (x["high"] - x["low"]).replace(0, np.nan)
    x["body_pct"] = x["body"] / x["range"]
    x["avg_body20"] = x["body"].rolling(20, min_periods=5).mean()
    return x

def near_level(value, level, tolerance_pct):
    if level == 0 or pd.isna(level):
        return False
    return abs(value - level) / abs(level) * 100 <= tolerance_pct

def scan_abandoned_baby(
    df,
    pattern,
    ema_len=200,
    sr_tolerance=0.50,
    doji_max_body_pct=0.10,
    long_body_factor=1.20,
    require_ema_slope=True
):
    """
    IMPORTANT:
    Bullish:
      D1 = long red
      D2 = doji, fully below D1 low
      D3 = long green, fully above D2 high,
           and D3 CLOSE > D1 OPEN
      PLUS: pattern is actually at EMA SUPPORT:
        - EMA is within tolerance of D1/D2/D3 support area, OR
        - EMA lies inside the pattern's price zone
        - D3 closes back ABOVE EMA

    Bearish is the exact mirror:
      D1 = long green
      D2 = doji, fully above D1 high
      D3 = long red, fully below D2 low,
           and D3 CLOSE < D1 OPEN
      PLUS: pattern is actually at EMA RESISTANCE:
        - EMA is within tolerance of D1/D2/D3 resistance area, OR
        - EMA lies inside pattern price zone
        - D3 closes back BELOW EMA
    """
    x = prepare(df, ema_len)
    out = []

    for i in range(2, len(x)):
        d1, d2, d3 = x.iloc[i-2], x.iloc[i-1], x.iloc[i]

        if any(pd.isna(d1[c]) for c in ["avg_body20", "ema"]) or pd.isna(d2["ema"]) or pd.isna(d3["ema"]):
            continue

        d1_long = d1["body"] >= d1["avg_body20"] * long_body_factor
        d3_long = d3["body"] >= d3["avg_body20"] * long_body_factor
        d2_doji = d2["range"] > 0 and d2["body_pct"] <= doji_max_body_pct

        # Exact three-candle definitions supplied by user
        bullish_pattern = (
            d1["close"] < d1["open"] and
            d1_long and
            d2_doji and
            d2["high"] < d1["low"] and
            d3["close"] > d3["open"] and
            d3_long and
            d3["low"] > d2["high"] and
            d3["close"] > d1["open"]
        )

        bearish_pattern = (
            d1["close"] > d1["open"] and
            d1_long and
            d2_doji and
            d2["low"] > d1["high"] and
            d3["close"] < d3["open"] and
            d3_long and
            d3["high"] < d2["low"] and
            d3["close"] < d1["open"]
        )

        # ----------------------------------------------------
        # EMA SUPPORT / RESISTANCE
        # We do NOT merely ask whether price is "near" EMA.
        # The pattern must interact with the EMA zone.
        # ----------------------------------------------------
        ema = float(d2["ema"])
        ema1, ema3 = float(d1["ema"]), float(d3["ema"])

        # Bullish support:
        # EMA must be close to the pattern's lower/support structure,
        # or pass through the 3-candle price area, and confirmation
        # candle must recover/close above EMA.
        bullish_support_touch = (
            near_level(d1["low"], ema1, sr_tolerance) or
            near_level(d2["low"], ema, sr_tolerance) or
            near_level(d3["low"], ema3, sr_tolerance) or
            (min(d1["low"], d2["low"], d3["low"]) <= ema <=
             max(d1["high"], d2["high"], d3["high"]))
        )
        bullish_reclaim = d3["close"] > ema3

        # Bearish resistance:
        # EMA must be close to pattern's upper/resistance structure,
        # or pass through the 3-candle price area, and confirmation
        # candle must close below EMA.
        bearish_resistance_touch = (
            near_level(d1["high"], ema1, sr_tolerance) or
            near_level(d2["high"], ema, sr_tolerance) or
            near_level(d3["high"], ema3, sr_tolerance) or
            (min(d1["low"], d2["low"], d3["low"]) <= ema <=
             max(d1["high"], d2["high"], d3["high"]))
        )
        bearish_reject = d3["close"] < ema3

        if require_ema_slope:
            bullish_slope = ema3 > ema1
            bearish_slope = ema3 < ema1
        else:
            bullish_slope = True
            bearish_slope = True

        if pattern == "Bullish Abandoned Baby":
            valid = bullish_pattern and bullish_support_touch and bullish_reclaim and bullish_slope
            if valid:
                out.append({
                    "Signal": "BULLISH",
                    "Date": d3["date"],
                    "D1": d1["date"],
                    "D2": d2["date"],
                    "D3": d3["date"],
                    "Close": d3["close"],
                    f"EMA{ema_len}": d3["ema"],
                    "Support Test": "YES",
                    "EMA Slope": "UP" if ema3 > ema1 else "FLAT",
                    "D1 Open": d1["open"],
                    "D1 Low": d1["low"],
                    "D2 High": d2["high"],
                    "D3 Low": d3["low"],
                })

        else:
            valid = bearish_pattern and bearish_resistance_touch and bearish_reject and bearish_slope
            if valid:
                out.append({
                    "Signal": "BEARISH",
                    "Date": d3["date"],
                    "D1": d1["date"],
                    "D2": d2["date"],
                    "D3": d3["date"],
                    "Close": d3["close"],
                    f"EMA{ema_len}": d3["ema"],
                    "Resistance Test": "YES",
                    "EMA Slope": "DOWN" if ema3 < ema1 else "FLAT",
                    "D1 Open": d1["open"],
                    "D1 High": d1["high"],
                    "D2 Low": d2["low"],
                    "D3 High": d3["high"],
                })

    return pd.DataFrame(out)

# ============================================================
# UI
# ============================================================
st.title("🔎 Abandoned Baby — EMA Support / Resistance Scanner")
st.caption("One scanner • switch Bullish/Bearish • adjustable timeframe • adjustable EMA")

if "results" not in st.session_state:
    st.session_state.results = pd.DataFrame()

with st.sidebar:
    st.header("1. Pattern")

    pattern = st.radio(
        "Scan",
        ["Bullish Abandoned Baby", "Bearish Abandoned Baby"],
        horizontal=False
    )

    st.header("2. Timeframe")

    timeframe_label = st.selectbox(
        "Timeframe",
        ["1 Minute", "3 Minutes", "5 Minutes", "10 Minutes",
         "15 Minutes", "30 Minutes", "1 Hour", "1 Day"],
        index=7
    )

    interval = {
        "1 Minute": "ONE_MINUTE",
        "3 Minutes": "THREE_MINUTE",
        "5 Minutes": "FIVE_MINUTE",
        "10 Minutes": "TEN_MINUTE",
        "15 Minutes": "FIFTEEN_MINUTE",
        "30 Minutes": "THIRTY_MINUTE",
        "1 Hour": "ONE_HOUR",
        "1 Day": "ONE_DAY",
    }[timeframe_label]

    st.header("3. EMA Support / Resistance")

    ema_len = st.number_input(
        "EMA Length",
        min_value=2,
        max_value=1000,
        value=200,
        step=1,
        help="Change this to 20, 50, 100, 200, etc. The scanner recalculates this EMA from the selected timeframe."
    )

    sr_tolerance = st.number_input(
        "EMA S/R touch tolerance (%)",
        min_value=0.05,
        max_value=5.0,
        value=0.50,
        step=0.05,
        help="How close a candle's high/low must be to the EMA to count as a support/resistance test."
    )

    require_slope = st.checkbox(
        "Require EMA slope",
        value=True,
        help="Bullish requires EMA rising. Bearish requires EMA falling."
    )

    st.header("4. Candle Definition")

    doji_pct = st.number_input(
        "Doji max body / range",
        min_value=0.01,
        max_value=0.50,
        value=0.10,
        step=0.01
    )

    long_factor = st.number_input(
        "Long candle = body × 20-candle average",
        min_value=0.50,
        max_value=5.0,
        value=1.20,
        step=0.05
    )

    days = st.number_input(
        "Historical days",
        min_value=1,
        max_value=3650,
        value=365,
        step=1
    )

    st.header("5. Data")
    source = st.radio("Source", ["Angel One API", "Upload CSV"])

    run = st.button("🔍 RUN SCANNER", type="primary", use_container_width=True)

symbols_default = [
    "ASTRAL","CONCOR","KALYANKJIL","GODREJCP","BDL","PAYTM","JUBLFOOD",
    "TMPV","BEL","TECHM","SHRIRAMFIN","TATAPOWER","DLF","NTPC","ITC",
    "PFC","SWIGGY","KOTAKBANK","BHARTIARTL","MCX","RECLTD","SBIN",
    "COALINDIA","HDFCBANK","INDUSTOWER","BPCL","LICI","INFY","POWERGRID",
    "BSE","ADANIENSOL","AXISBANK","HINDZINC","RELIANCE","ICICIBANK",
    "SBICARD","VEDL","HINDALCO","NATIONALUM"
]

st.subheader("Symbols")
symbol_text = st.text_area("NSE symbols", "\n".join(symbols_default), height=170)
symbols = [s.strip().upper() for s in symbol_text.replace(",", "\n").splitlines() if s.strip()]

# ============================================================
# RUN
# ============================================================
if run:
    combined = []

    if source == "Upload CSV":
        uploaded = st.file_uploader(
            "Upload OHLC CSV with date, open, high, low, close",
            type=["csv"],
            key="ohlc_upload"
        )

        if uploaded is None:
            st.warning("Upload the CSV and press RUN SCANNER again.")
        else:
            df = pd.read_csv(uploaded)
            df.columns = [c.strip().lower() for c in df.columns]

            needed = {"date", "open", "high", "low", "close"}
            if not needed.issubset(df.columns):
                st.error("CSV must contain: date, open, high, low, close")
            else:
                df["date"] = pd.to_datetime(df["date"])
                result = scan_abandoned_baby(
                    df, pattern, ema_len, sr_tolerance,
                    doji_pct, long_factor, require_slope
                )
                if not result.empty:
                    result.insert(0, "Symbol", "CSV")
                    combined.append(result)

    else:
        try:
            client = AngelOneClient.from_streamlit_secrets()
        except Exception as e:
            st.error(str(e))
            client = None

        if client:
            progress = st.progress(0)
            status = st.empty()

            for n, symbol in enumerate(symbols, start=1):
                status.write(f"Scanning {symbol} — {n}/{len(symbols)}")
                try:
                    df = client.get_historical(symbol, interval, int(days))

                    if df is None or len(df) < max(30, int(ema_len) + 5):
                        continue

                    result = scan_abandoned_baby(
                        df, pattern, ema_len, sr_tolerance,
                        doji_pct, long_factor, require_slope
                    )

                    if not result.empty:
                        result.insert(0, "Symbol", symbol)
                        combined.append(result)

                except Exception as e:
                    st.warning(f"{symbol}: {e}")

                progress.progress(n / len(symbols))

            status.success("Scan completed.")

    st.session_state.results = (
        pd.concat(combined, ignore_index=True)
        if combined else pd.DataFrame()
    )

# ============================================================
# RESULTS
# ============================================================
st.divider()
st.subheader(f"{pattern} Signals")

result = st.session_state.results

if result.empty:
    st.info("No signals found with the selected settings.")
else:
    st.success(f"{len(result)} signal(s) found")
    st.dataframe(result, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Download Signals CSV",
        result.to_csv(index=False).encode("utf-8"),
        "abandoned_baby_signals.csv",
        "text/csv"
    )

st.divider()
st.subheader("Scanner Logic")

if pattern == "Bullish Abandoned Baby":
    st.markdown("""
**Bullish pattern**
- D1 = long red
- D2 = doji
- D2 High < D1 Low
- D3 = long green
- D3 Low > D2 High
- D3 Close > D1 Open

**Support requirement**
- Selected EMA must actually interact with the 3-candle support area.
- D3 must close back above the selected EMA.
- If EMA-slope filter is ON, EMA must be rising.
""")
else:
    st.markdown("""
**Bearish pattern**
- D1 = long green
- D2 = doji
- D2 Low > D1 High
- D3 = long red
- D3 High < D2 Low
- D3 Close < D1 Open

**Resistance requirement**
- Selected EMA must actually interact with the 3-candle resistance area.
- D3 must close back below the selected EMA.
- If EMA-slope filter is ON, EMA must be falling.
""")

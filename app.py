"""
Abandoned Baby Pattern Scanner (Bullish / Bearish) — powered by Upstox API.

Run locally:
    streamlit run app.py

Deploy: push this folder to a GitHub repo and deploy on Streamlit Community Cloud
(share.streamlit.io) pointing at app.py. See README.md for full instructions.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from core import upstox_api as api
from core import pivots as pv
from core import patterns as pat
from core.charting import build_pattern_chart

st.set_page_config(page_title="Abandoned Baby Scanner", layout="wide", page_icon="🕯️")

DEFAULT_WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "ITC",
    "LT", "AXISBANK", "KOTAKBANK", "BAJFINANCE", "HINDUNILVR", "MARUTI",
    "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "ADANIENT", "BHARTIARTL",
    "WIPRO", "ULTRACEMCO",
]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "pattern_mode" not in st.session_state:
    st.session_state.pattern_mode = "Bullish"
if "scan_results" not in st.session_state:
    st.session_state.scan_results = []

# ---------------------------------------------------------------------------
# Sidebar — configuration
# ---------------------------------------------------------------------------
st.sidebar.title("🕯️ Scanner Settings")

access_token = st.sidebar.text_input(
    "Upstox Access Token",
    type="password",
    value=st.secrets.get("UPSTOX_ACCESS_TOKEN", "") if hasattr(st, "secrets") else "",
    help="Generate a daily access token from your Upstox Developer app. See README for steps.",
)

st.sidebar.markdown("### Pattern")
mode_col1, mode_col2 = st.sidebar.columns(2)
if mode_col1.button("🟢 Bullish", use_container_width=True, type="primary" if st.session_state.pattern_mode == "Bullish" else "secondary"):
    st.session_state.pattern_mode = "Bullish"
if mode_col2.button("🔴 Bearish", use_container_width=True, type="primary" if st.session_state.pattern_mode == "Bearish" else "secondary"):
    st.session_state.pattern_mode = "Bearish"

scan_both = st.sidebar.checkbox("Scan both patterns at once", value=False)
pattern_type = "Both" if scan_both else st.session_state.pattern_mode

st.sidebar.markdown(f"**Currently scanning:** `{pattern_type} Abandoned Baby`")

st.sidebar.markdown("### Timeframe")
timeframe_label = st.sidebar.selectbox(
    "Candle timeframe", list(api.TIMEFRAMES.keys()), index=list(api.TIMEFRAMES.keys()).index("1 day")
)

lookback_default = api.DEFAULT_LOOKBACK_DAYS[timeframe_label]
lookback_days = st.sidebar.number_input(
    "Lookback (calendar days)", min_value=5, max_value=3650, value=lookback_default, step=5,
    help="How far back to pull candles for scanning + pivot calc.",
)

st.sidebar.markdown("### Pivot Points (Support / Resistance)")
pivot_basis = st.sidebar.selectbox("Pivot basis", ["Daily", "Weekly", "Monthly"], index=0,
                                    help="Pivot levels are computed from the PRIOR day/week/month's high-low-close.")
tolerance_pct = st.sidebar.slider(
    "Proximity tolerance to S/R (%)", min_value=0.05, max_value=3.0, value=0.5, step=0.05,
    help="Day 2 (the doji) must fall within this % distance of a pivot level to count as 'at support/resistance'.",
)

with st.sidebar.expander("Advanced pattern thresholds"):
    body_ratio_threshold = st.slider(
        "Min body/range ratio for 'long' candle", 0.3, 0.9, 0.55, 0.05,
        help="Day1 & Day3 body size as a fraction of their high-low range, to qualify as a long candle.",
    )
    doji_ratio_threshold = st.slider(
        "Max body/range ratio for doji", 0.02, 0.3, 0.12, 0.01,
        help="Day2 body size as a fraction of its high-low range, to qualify as a doji.",
    )

st.sidebar.markdown("### Watchlist")
watchlist_source = st.sidebar.radio("Symbols to scan", ["Default NIFTY watchlist", "Custom list"], index=0)
if watchlist_source == "Custom list":
    custom_text = st.sidebar.text_area(
        "Enter NSE trading symbols, comma or newline separated",
        value="RELIANCE, TCS, HDFCBANK",
        height=100,
    )
    symbols = [s.strip().upper() for s in custom_text.replace("\n", ",").split(",") if s.strip()]
else:
    symbols = DEFAULT_WATCHLIST

run_scan = st.sidebar.button("🔍 Run Scan", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------
st.title("🕯️ Abandoned Baby Pattern Scanner")
st.caption(
    "Detects Bullish & Bearish Abandoned Baby reversal candles that form exactly at a pivot "
    "support/resistance level, using live/historical data from the Upstox API."
)

with st.expander("Pattern rules used by this scanner", expanded=False):
    st.markdown(
        """
**Bullish Abandoned Baby** (must form near a pivot **support** level)
1. Day 1 — long red/black candle
2. Day 2 — doji that gaps fully *below* Day 1's low
3. Day 3 — long green/white candle that gaps fully *above* Day 2's high **and closes above Day 1's open**

**Bearish Abandoned Baby** (must form near a pivot **resistance** level)
1. Day 1 — long green/white candle
2. Day 2 — doji that gaps fully *above* Day 1's high
3. Day 3 — long red/black candle that gaps fully *below* Day 2's low **and closes below Day 1's open**
        """
    )

if not access_token:
    st.info("👈 Enter your Upstox access token in the sidebar to begin.")
    st.stop()

if run_scan:
    if not symbols:
        st.warning("Add at least one symbol to your watchlist.")
        st.stop()

    to_date = dt.date.today()
    from_date = to_date - dt.timedelta(days=int(lookback_days))

    with st.spinner("Loading Upstox instrument master..."):
        try:
            master_df = api.load_instrument_master()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not load instrument master file: {e}")
            st.stop()

    results = []
    progress = st.progress(0.0, text="Starting scan...")
    errors = []

    for i, symbol in enumerate(symbols):
        progress.progress((i + 1) / len(symbols), text=f"Scanning {symbol} ({i + 1}/{len(symbols)})")

        instrument_key = api.resolve_instrument_key(master_df, symbol, exchange="NSE_EQ")
        if not instrument_key:
            errors.append(f"{symbol}: instrument key not found in NSE_EQ master list")
            continue

        try:
            df = api.get_historical_candles(access_token, instrument_key, timeframe_label, from_date, to_date)
        except api.UpstoxAPIError as e:
            errors.append(str(e))
            continue

        if df.empty or len(df) < 3:
            continue

        # Always compute DAILY OHLC (needed as the basis for pivot calc regardless of chart timeframe)
        try:
            daily_df = api.get_historical_candles(access_token, instrument_key, "1 day", from_date, to_date)
        except api.UpstoxAPIError as e:
            errors.append(f"{symbol} (daily pivot data): {e}")
            continue

        if daily_df.empty:
            continue

        pivot_table = pv.build_pivot_table(daily_df, basis=pivot_basis)
        df_with_pivots = pv.attach_pivots(df, pivot_table)

        matches = pat.detect_patterns(
            df_with_pivots,
            symbol=symbol,
            pattern_type=pattern_type,
            body_ratio_threshold=body_ratio_threshold,
            doji_ratio_threshold=doji_ratio_threshold,
            tolerance_pct=tolerance_pct,
        )
        for m in matches:
            results.append((m, df_with_pivots))

    progress.empty()
    st.session_state.scan_results = results

    if errors:
        with st.expander(f"⚠️ {len(errors)} symbol(s) had issues", expanded=False):
            for e in errors:
                st.write(f"- {e}")

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------
results = st.session_state.scan_results

if results:
    st.success(f"Found {len(results)} pattern match(es).")

    rows = []
    for m, _ in results:
        rows.append(
            {
                "Symbol": m.symbol,
                "Pattern": m.pattern,
                "Day3 Time": m.day3_time,
                "Level Matched": m.level_name,
                "Level Value": round(m.level_value, 2),
                "Distance %": round(m.distance_pct, 3),
                "Day3 Close": round(m.day3["close"], 2),
            }
        )
    result_df = pd.DataFrame(rows).sort_values("Day3 Time", ascending=False)
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    st.markdown("### Charts")
    symbol_choice = st.selectbox(
        "Select a match to view its chart",
        options=list(range(len(results))),
        format_func=lambda i: f"{results[i][0].symbol} — {results[i][0].pattern} — {results[i][0].day3_time}",
    )
    match, chart_df = results[symbol_choice]
    fig = build_pattern_chart(chart_df, match)
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Day 1 (setup)", f"O {match.day1['open']:.2f} / C {match.day1['close']:.2f}")
    c2.metric("Day 2 (doji)", f"H {match.day2['high']:.2f} / L {match.day2['low']:.2f}")
    c3.metric("Day 3 (confirmation)", f"O {match.day3['open']:.2f} / C {match.day3['close']:.2f}")

elif run_scan:
    st.warning("No matching patterns found for the current settings. Try widening the S/R tolerance or lookback window.")
else:
    st.caption("Configure your settings in the sidebar and click **Run Scan**.")

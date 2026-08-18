"""
Abandoned Baby Scanner -- Streamlit web app
=============================================

Browser-based version of the scanner with real, clickable buttons to switch
between Bullish / Bearish / Both. Deploy this straight from a GitHub repo to
Streamlit Community Cloud (share.streamlit.io):

    1. Push this file + scanner_core.py + requirements.txt to a GitHub repo.
    2. Go to share.streamlit.io -> "New app" -> pick the repo/branch ->
       set "Main file path" to streamlit_app.py -> Deploy.

Run locally with:
    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""

import pandas as pd
import streamlit as st

from scanner_core import scan_tickers, add_indicators, fetch_ohlc, PATTERN_FUNCS

st.set_page_config(page_title="Abandoned Baby Scanner", layout="wide")

st.title("🕯️ Abandoned Baby Scanner")
st.caption("Bullish & Bearish Abandoned Baby candlestick scanner, filtered by an EMA support/resistance test.")

# --------------------------------------------------------------------------
# Sidebar: all the settings
# --------------------------------------------------------------------------

with st.sidebar:
    st.header("Settings")

    tickers_raw = st.text_area(
        "Tickers (comma or space separated)",
        value="RELIANCE, TCS, INFY, HDFCBANK",
        height=80,
    )

    market = st.selectbox("Market", ["NSE", "US", "None (use tickers as typed)"], index=0)

    interval = st.selectbox(
        "Timeframe",
        ["1d", "1wk", "1mo", "1h", "30m", "15m", "5m"],
        index=0,
        help="Intraday intervals (below 1h) are limited by Yahoo Finance to roughly the last 60 days.",
    )

    period = st.text_input(
        "History period",
        value="3y",
        help="How much history to pull, e.g. 6mo, 1y, 3y, 5y, max. "
             "Must comfortably exceed the EMA length in bars.",
    )

    ema_length = st.number_input("EMA length", min_value=5, max_value=500, value=200, step=1)

    st.markdown("---")
    st.subheader("Pattern strictness")
    ema_tolerance_pct = st.slider("EMA tolerance (%)", 0.5, 10.0, 3.0, 0.5) / 100
    doji_body_pct = st.slider("Max doji body (% of range)", 2, 30, 10, 1) / 100
    long_body_mult = st.slider("Min body size (x 20-bar avg)", 0.5, 3.0, 1.0, 0.1)
    loose_gap = st.checkbox("Use loose gaps (body-only) instead of strict island gaps", value=False)

# --------------------------------------------------------------------------
# Main area: the pattern switch (buttons) + Run button
# --------------------------------------------------------------------------

st.subheader("Pattern")
if "pattern" not in st.session_state:
    st.session_state.pattern = "both"

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("📈 Bullish Abandoned Baby", use_container_width=True,
                 type="primary" if st.session_state.pattern == "bullish" else "secondary"):
        st.session_state.pattern = "bullish"
with col2:
    if st.button("📉 Bearish Abandoned Baby", use_container_width=True,
                 type="primary" if st.session_state.pattern == "bearish" else "secondary"):
        st.session_state.pattern = "bearish"
with col3:
    if st.button("🔀 Both", use_container_width=True,
                 type="primary" if st.session_state.pattern == "both" else "secondary"):
        st.session_state.pattern = "both"

st.caption(f"Currently scanning for: **{st.session_state.pattern.upper()}**")

run = st.button("▶️ Run Scan", type="primary")

# --------------------------------------------------------------------------
# Run the scan
# --------------------------------------------------------------------------

def parse_tickers(raw: str, market: str):
    parts = [p.strip() for chunk in raw.split(",") for p in chunk.split() if p.strip()]
    if market == "NSE":
        parts = [p if p.upper().endswith(".NS") else f"{p}.NS" for p in parts]
    return parts


if run:
    tickers = parse_tickers(tickers_raw, market)
    if not tickers:
        st.warning("Enter at least one ticker.")
        st.stop()

    progress = st.progress(0.0, text="Starting scan...")
    log_box = st.empty()
    log_lines = []

    results = {}
    funcs = PATTERN_FUNCS if st.session_state.pattern == "both" else {
        st.session_state.pattern: PATTERN_FUNCS[st.session_state.pattern]
    }

    for idx, t in enumerate(tickers):
        progress.progress((idx) / len(tickers), text=f"Scanning {t}...")
        try:
            df = fetch_ohlc(t, period=period, interval=interval)
            if df.empty or len(df) < ema_length + 10:
                log_lines.append(f"⏭️ {t}: not enough data ({len(df)} bars) for a {ema_length}-period EMA")
                continue
            df = add_indicators(df, ema_length=ema_length)

            all_hits = []
            for label, fn in funcs.items():
                hits = fn(
                    df,
                    doji_body_pct=doji_body_pct,
                    long_body_mult=long_body_mult,
                    ema_tolerance_pct=ema_tolerance_pct,
                    strict_gap=not loose_gap,
                )
                for h in hits:
                    h["pattern"] = label
                all_hits.extend(hits)
            all_hits.sort(key=lambda h: h["day3_date"])

            if all_hits:
                results[t] = all_hits
                log_lines.append(f"✅ {t}: {len(all_hits)} pattern(s) found")
            else:
                log_lines.append(f"— {t}: no match")
        except Exception as e:
            log_lines.append(f"⚠️ {t}: error -- {e}")

        log_box.text("\n".join(log_lines))

    progress.progress(1.0, text="Done")

    st.markdown("---")
    st.subheader("Results")

    if not results:
        st.info(f"No {st.session_state.pattern} abandoned baby pattern(s) found for the given tickers/settings.")
    else:
        rows = []
        for t, hits in results.items():
            for h in hits:
                rows.append({
                    "Ticker": t,
                    "Pattern": h["pattern"].capitalize(),
                    "Day 1": h["day1_date"].date(),
                    "Day 1 Open": h["day1_open"],
                    "Day 1 Close": h["day1_close"],
                    "Day 2 (Doji)": h["day2_date"].date(),
                    "Doji Close": h["day2_doji_close"],
                    f"EMA{ema_length} @ Doji": h["ema_at_doji"],
                    "Day 3 (Confirm)": h["day3_date"].date(),
                    "Day 3 Close": h["day3_close"],
                })
        result_df = pd.DataFrame(rows).sort_values(["Day 3 (Confirm)", "Ticker"], ascending=[False, True])
        st.dataframe(result_df, use_container_width=True, hide_index=True)

        csv = result_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download results as CSV", csv, "abandoned_baby_matches.csv", "text/csv")
else:
    st.info("Set your tickers and settings in the sidebar, pick a pattern above, then click **Run Scan**.")

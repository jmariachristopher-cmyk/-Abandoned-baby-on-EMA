# Abandoned Baby Scanner

Scans stocks for the **Bullish** and **Bearish Abandoned Baby** candlestick patterns,
filtered by a support/resistance test against an EMA (default 200-period).

## Files

- `scanner_core.py` — the tested pattern-detection engine (shared by both tools below).
- `streamlit_app.py` — browser-based app with buttons to switch between Bullish / Bearish / Both. **Use this for Streamlit Cloud.**
- `abandoned_baby_scanner.py` — command-line tool, also has an optional Tkinter desktop GUI (`--gui`, needs a local display, won't work on Streamlit Cloud).
- `requirements.txt` — dependencies for `pip install -r requirements.txt`.

## Run locally

```bash
pip install -r requirements.txt

# Web app
streamlit run streamlit_app.py

# Command line
python abandoned_baby_scanner.py --tickers RELIANCE TCS INFY --market NSE --pattern bullish

# Desktop GUI (needs a display, not for servers/Cloud)
python abandoned_baby_scanner.py --gui
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**.
3. Pick your repo/branch, set **Main file path** to `streamlit_app.py`.
4. Deploy. The `requirements.txt` in the repo root is picked up automatically.

## Pattern definitions

**Bullish Abandoned Baby**
1. Day 1 — long red/black candle
2. Day 2 — doji that gaps fully below Day 1's low
3. Day 3 — long green/white candle that gaps fully above Day 2's high **and closes above Day 1's open**

**Bearish Abandoned Baby** (mirror image)
1. Day 1 — long green/white candle
2. Day 2 — doji that gaps fully above Day 1's high
3. Day 3 — long red/black candle that gaps fully below Day 2's low **and closes below Day 1's open**

**EMA filter**: the doji must form at/near the EMA (support for bullish, resistance for bearish),
and Day 3 must close back through it — so only reversals happening at that EMA level get flagged.

# 🕯️ Abandoned Baby Pattern Scanner

Scans NSE stocks for **Bullish** and **Bearish Abandoned Baby** candlestick
patterns that form exactly at a **pivot support/resistance** level, using
live data from the **Upstox API**. Built with Streamlit.

## What it detects

**Bullish Abandoned Baby** — must form near a pivot **support** level
1. Day 1 — long red/black candle
2. Day 2 — doji that gaps fully *below* Day 1's low
3. Day 3 — long green/white candle that gaps fully *above* Day 2's high, **and closes above Day 1's open**

**Bearish Abandoned Baby** — must form near a pivot **resistance** level
1. Day 1 — long green/white candle
2. Day 2 — doji that gaps fully *above* Day 1's high
3. Day 3 — long red/black candle that gaps fully *below* Day 2's low, **and closes below Day 1's open**

The app has a toggle in the sidebar to switch between Bullish / Bearish (or
scan both at once), a timeframe dropdown (1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H,
1D, 1W, 1M — powered by Upstox's v3 candle API), and controls for pivot
basis (Daily/Weekly/Monthly) and how close (%) the doji needs to be to a
pivot level to count as "at support/resistance".

## Project structure

```
abandoned_baby_scanner/
├── app.py                    # Streamlit UI
├── core/
│   ├── upstox_api.py         # Upstox v3 historical candle + instrument master
│   ├── pivots.py             # Classic floor pivot point calculation
│   ├── patterns.py           # Abandoned Baby detection logic
│   └── charting.py           # Plotly candlestick chart builder
├── requirements.txt
├── .streamlit/secrets.toml.example
└── README.md
```

## 1. Get an Upstox Access Token

Upstox access tokens are valid for **one trading day** and must be
regenerated daily (there's no long-lived key). Steps:

1. Create a developer app at https://account.upstox.com/developer/apps
   (any placeholder Redirect URI works, e.g. `https://localhost`).
2. Note your **API Key (client_id)** and **API Secret (client_secret)**.
3. Open this URL in a browser (replace `YOUR_API_KEY` and `YOUR_REDIRECT_URI`):
   ```
   https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id=YOUR_API_KEY&redirect_uri=YOUR_REDIRECT_URI
   ```
4. Log in with your Upstox credentials. You'll be redirected to your
   redirect URI with a `?code=...` query parameter — copy that `code`.
5. Exchange the code for an access token:
   ```bash
   curl -X POST https://api.upstox.com/v2/login/authorization/token \
     -H 'accept: application/json' \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d 'code=THE_CODE' \
     -d 'client_id=YOUR_API_KEY' \
     -d 'client_secret=YOUR_API_SECRET' \
     -d 'redirect_uri=YOUR_REDIRECT_URI' \
     -d 'grant_type=authorization_code'
   ```
6. The response's `access_token` field is what you paste into the scanner's
   sidebar (or store as a Streamlit secret — see below).

Full docs: https://upstox.com/developer/api-documentation/authentication

## 2. Run locally

```bash
git clone <your-repo-url>
cd abandoned_baby_scanner
pip install -r requirements.txt
streamlit run app.py
```

Then paste your access token into the sidebar, pick a pattern/timeframe,
and click **Run Scan**.

Optionally, instead of pasting the token every time, copy
`.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in
`UPSTOX_ACCESS_TOKEN` — the app will pre-fill the token field from secrets.
**Never commit the real `secrets.toml` to GitHub** (it's already in
`.gitignore`).

## 3. Deploy on Streamlit Community Cloud via GitHub

1. Push this folder to a new GitHub repository.
2. Go to https://share.streamlit.io → **New app**.
3. Pick your repo/branch and set **Main file path** to `app.py`.
4. Under **Advanced settings → Secrets**, paste:
   ```toml
   UPSTOX_ACCESS_TOKEN = "your-daily-access-token"
   ```
   (You'll need to update this secret each trading day since Upstox tokens
   expire daily — or just paste a fresh token into the sidebar each session.)
5. Click **Deploy**. The app will be live at a `*.streamlit.app` URL.

## Notes & limitations

- Data availability windows follow Upstox's own limits per timeframe
  (roughly: 1-minute ≈ last 1 month, 30-minute ≈ last 1 year, daily/weekly/
  monthly ≈ several years). The scanner's default "Lookback" per timeframe
  is set conservatively inside those limits — adjust in the sidebar if
  needed.
- Pivot levels are always computed from **daily** OHLC (previous day, or
  previous week/month if you choose that basis) regardless of the chart
  timeframe you're scanning, which is standard practice for using pivots on
  intraday charts.
- This tool is for educational/technical-analysis purposes only and is not
  investment advice.

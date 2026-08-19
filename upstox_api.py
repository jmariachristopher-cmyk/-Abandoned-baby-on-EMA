"""
Thin wrapper around Upstox API v3 Historical Candle Data endpoint.

Docs: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data
GET /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}

unit     : "minutes" | "hours" | "days" | "weeks" | "months"
interval : integer step for that unit (e.g. unit=minutes, interval=15 -> 15-minute candles)
"""

from __future__ import annotations

import gzip
import json
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st

BASE_URL = "https://api.upstox.com/v3"
HISTORICAL_URL = f"{BASE_URL}/historical-candle"
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"

# Timeframe label -> (unit, interval) as required by the v3 API
TIMEFRAMES = {
    "1 minute": ("minutes", 1),
    "3 minute": ("minutes", 3),
    "5 minute": ("minutes", 5),
    "15 minute": ("minutes", 15),
    "30 minute": ("minutes", 30),
    "1 hour": ("hours", 1),
    "2 hour": ("hours", 2),
    "4 hour": ("hours", 4),
    "1 day": ("days", 1),
    "1 week": ("weeks", 1),
    "1 month": ("months", 1),
}

# Sensible default lookback windows per timeframe so a single request stays inside
# what the API will actually return, while still leaving room for pivot calc.
DEFAULT_LOOKBACK_DAYS = {
    "1 minute": 25,
    "3 minute": 25,
    "5 minute": 60,
    "15 minute": 90,
    "30 minute": 180,
    "1 hour": 250,
    "2 hour": 250,
    "4 hour": 400,
    "1 day": 900,
    "1 week": 1500,
    "1 month": 3650,
}

COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "oi"]


class UpstoxAPIError(Exception):
    pass


def _headers(access_token: str) -> dict:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }


def get_historical_candles(
    access_token: str,
    instrument_key: str,
    timeframe_label: str,
    from_date: date,
    to_date: date,
    max_retries: int = 2,
) -> pd.DataFrame:
    """Fetch historical OHLCV candles for a single instrument/timeframe.

    Returns a DataFrame sorted oldest -> newest with columns:
    timestamp, open, high, low, close, volume, oi
    """
    unit, interval = TIMEFRAMES[timeframe_label]
    key_enc = instrument_key  # requests handles the '|' fine inside the path
    url = (
        f"{HISTORICAL_URL}/{key_enc}/{unit}/{interval}/"
        f"{to_date.isoformat()}/{from_date.isoformat()}"
    )

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=_headers(access_token), timeout=20)
            if resp.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            payload = resp.json()
            candles = payload.get("data", {}).get("candles", [])
            df = pd.DataFrame(candles, columns=COLUMNS)
            if not df.empty:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                for c in ["open", "high", "low", "close", "volume"]:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                df = df.sort_values("timestamp").reset_index(drop=True)
            return df
        except requests.HTTPError as e:
            last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(0.8)

    raise UpstoxAPIError(f"Failed to fetch candles for {instrument_key} ({timeframe_label}): {last_err}")


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def load_instrument_master() -> pd.DataFrame:
    """Download & cache the Upstox complete instrument master file.

    Cached for 6 hours (Upstox refreshes it once daily around 6 AM IST).
    """
    resp = requests.get(INSTRUMENTS_URL, timeout=60)
    resp.raise_for_status()
    raw = gzip.decompress(resp.content)
    data = json.loads(raw)
    df = pd.DataFrame(data)

    # Field name has varied historically between 'trading_symbol' and 'tradingsymbol'
    if "trading_symbol" not in df.columns and "tradingsymbol" in df.columns:
        df["trading_symbol"] = df["tradingsymbol"]
    return df


def search_equity_instruments(master_df: pd.DataFrame, query: str, exchange: str = "NSE_EQ", limit: int = 25) -> pd.DataFrame:
    """Search the instrument master for equities/indices matching `query`."""
    if master_df.empty or not query:
        return master_df.iloc[0:0]

    df = master_df
    if "segment" in df.columns:
        df = df[df["segment"] == exchange]
    elif "exchange" in df.columns:
        df = df[df["exchange"] == exchange.split("_")[0]]

    q = query.strip().upper()
    mask = pd.Series(False, index=df.index)
    for col in ["trading_symbol", "name"]:
        if col in df.columns:
            mask = mask | df[col].astype(str).str.upper().str.contains(q, na=False)
    return df[mask].head(limit)


def resolve_instrument_key(master_df: pd.DataFrame, symbol: str, exchange: str = "NSE_EQ") -> str | None:
    """Resolve a plain trading symbol (e.g. 'RELIANCE') to an Upstox instrument_key."""
    if master_df.empty:
        return None
    df = master_df
    if "segment" in df.columns:
        df = df[df["segment"] == exchange]
    sym = symbol.strip().upper()
    if "trading_symbol" in df.columns:
        hit = df[df["trading_symbol"].astype(str).str.upper() == sym]
        if not hit.empty:
            return hit.iloc[0]["instrument_key"]
    return None

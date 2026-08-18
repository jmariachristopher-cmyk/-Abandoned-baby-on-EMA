import time
from datetime import datetime, timedelta

import pandas as pd
import requests

try:
    from SmartApi import SmartConnect
except ImportError:
    SmartConnect = None

try:
    import pyotp
except ImportError:
    pyotp = None


SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)

# Maximum date span per Angel One historical request.
MAX_DAYS = {
    "ONE_MINUTE": 30,
    "THREE_MINUTE": 60,
    "FIVE_MINUTE": 100,
    "TEN_MINUTE": 100,
    "FIFTEEN_MINUTE": 200,
    "THIRTY_MINUTE": 200,
    "ONE_HOUR": 400,
    "ONE_DAY": 2000,
}


class AngelOneClient:
    def __init__(self, api_key, client_id, pin, totp_secret):
        if SmartConnect is None:
            raise RuntimeError("smartapi-python is not installed.")
        if pyotp is None:
            raise RuntimeError("pyotp is not installed.")

        self.smart = SmartConnect(api_key=api_key)

        totp = pyotp.TOTP(totp_secret).now()
        response = self.smart.generateSession(client_id, pin, totp)

        if not response or response.get("status") is not True:
            raise RuntimeError(f"Angel One login failed: {response}")

        self.client_id = client_id
        self._instrument_master = None
        self._last_candle_request = 0.0

    @classmethod
    def from_streamlit_secrets(cls):
        import streamlit as st

        required = [
            "ANGEL_API_KEY",
            "ANGEL_CLIENT_ID",
            "ANGEL_PIN",
            "ANGEL_TOTP_SECRET",
        ]
        missing = [x for x in required if x not in st.secrets]

        if missing:
            raise RuntimeError(
                "Missing Streamlit Secrets: " + ", ".join(missing)
            )

        return cls(
            st.secrets["ANGEL_API_KEY"],
            st.secrets["ANGEL_CLIENT_ID"],
            st.secrets["ANGEL_PIN"],
            st.secrets["ANGEL_TOTP_SECRET"],
        )

    def _load_instrument_master(self):
        if self._instrument_master is not None:
            return self._instrument_master

        r = requests.get(SCRIP_MASTER_URL, timeout=30)
        r.raise_for_status()
        data = r.json()

        # Keep only NSE cash equities.
        master = {}
        for item in data:
            if item.get("exch_seg") != "NSE":
                continue

            symbol = str(item.get("symbol", "")).upper()
            name = str(item.get("name", "")).upper()
            token = item.get("token")

            if not token:
                continue

            # Equity records normally end with -EQ.
            if symbol.endswith("-EQ"):
                master[name] = str(token)
                master[symbol[:-3]] = str(token)

        self._instrument_master = master
        return master

    def _token_lookup(self, symbol):
        symbol = symbol.strip().upper()
        master = self._load_instrument_master()

        if symbol in master:
            return master[symbol]

        # Fall back to Angel One searchScrip only if necessary.
        # searchScrip is rate-limited, so we use it only for a missing symbol.
        try:
            response = self.smart.searchScrip("NSE", symbol)
            data = response.get("data") if response else None

            if data:
                exact = [
                    x for x in data
                    if str(x.get("tradingsymbol", "")).upper() == symbol
                    and x.get("exch_seg") == "NSE"
                ]
                if exact:
                    return str(exact[0]["symboltoken"])
        except Exception:
            pass

        raise RuntimeError(f"NSE equity token not found for {symbol}")

    def _wait_for_historical_rate_limit(self):
        # Angel One documents 3 getCandleData requests/second.
        elapsed = time.monotonic() - self._last_candle_request
        wait = 0.40 - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_candle_request = time.monotonic()

    def _get_candle_chunk(self, token, interval, start, end):
        self._wait_for_historical_rate_limit()

        params = {
            "exchange": "NSE",
            "symboltoken": str(token),
            "interval": interval,
            "fromdate": start.strftime("%Y-%m-%d %H:%M"),
            "todate": end.strftime("%Y-%m-%d %H:%M"),
        }

        response = self.smart.getCandleData(params)

        if not response or response.get("status") is not True:
            raise RuntimeError(f"Historical API failed: {response}")

        rows = response.get("data") or []
        if not rows:
            return pd.DataFrame(
                columns=["date", "open", "high", "low", "close", "volume"]
            )

        return pd.DataFrame(
            rows,
            columns=["date", "open", "high", "low", "close", "volume"]
        )

    def get_historical(self, symbol, interval, days=365):
        token = self._token_lookup(symbol)

        days = int(days)
        max_span = MAX_DAYS.get(interval, 100)
        end = datetime.now()
        start = end - timedelta(days=days)

        frames = []
        chunk_start = start

        while chunk_start < end:
            chunk_end = min(
                chunk_start + timedelta(days=max_span),
                end
            )

            frame = self._get_candle_chunk(
                token, interval, chunk_start, chunk_end
            )
            if not frame.empty:
                frames.append(frame)

            # Avoid duplicate boundary candles.
            chunk_start = chunk_end + timedelta(minutes=1)

        if not frames:
            return pd.DataFrame(
                columns=["date", "open", "high", "low", "close", "volume"]
            )

        df = pd.concat(frames, ignore_index=True)
        df["date"] = pd.to_datetime(df["date"])

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return (
            df.dropna(subset=["open", "high", "low", "close"])
              .sort_values("date")
              .drop_duplicates("date")
              .reset_index(drop=True)
        )

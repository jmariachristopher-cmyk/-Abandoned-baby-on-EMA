# Abandoned Baby EMA Support/Resistance Scanner V2

The scanner now treats the selected EMA as a real support/resistance zone, not merely a trend filter.

## Bullish
- D1 long red
- D2 doji
- D2 High < D1 Low
- D3 long green
- D3 Low > D2 High
- D3 Close > D1 Open
- EMA interacts with the pattern support area
- D3 closes above EMA
- Optional EMA rising filter

## Bearish
- D1 long green
- D2 doji
- D2 Low > D1 High
- D3 long red
- D3 High < D2 Low
- D3 Close < D1 Open
- EMA interacts with the pattern resistance area
- D3 closes below EMA
- Optional EMA falling filter

## Adjustable
- Pattern direction
- Timeframe
- EMA length: 20/50/100/200/etc.
- EMA S/R touch tolerance
- Doji threshold
- Long candle threshold
- EMA slope requirement
- Historical days

Put Angel One credentials in Streamlit Secrets, never in GitHub.

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from . import pivots as pv


def build_pattern_chart(df: pd.DataFrame, match, context_bars: int = 15) -> go.Figure:
    """Build a candlestick chart around the 3-candle pattern, with the matched
    pivot level drawn as a horizontal line."""
    d3_time = match.day3_time
    idx = df.index[df["timestamp"] == d3_time]
    end_i = idx[0] if len(idx) else len(df) - 1
    start_i = max(0, end_i - context_bars)
    window = df.iloc[start_i : end_i + 2].copy()

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=window["timestamp"],
                open=window["open"],
                high=window["high"],
                low=window["low"],
                close=window["close"],
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
                name=match.symbol,
            )
        ]
    )

    fig.add_hline(
        y=match.level_value,
        line_dash="dot",
        line_color="#f5a623",
        annotation_text=f"{match.level_name} ({match.level_value:.2f})",
        annotation_position="top left",
    )

    for label, ts in [("Day1", match.day1_time), ("Day2 (doji)", match.day2_time), ("Day3", match.day3_time)]:
        fig.add_vline(x=ts, line_width=1, line_dash="dash", line_color="#888")

    fig.update_layout(
        title=f"{match.symbol} — {match.pattern}",
        xaxis_rangeslider_visible=False,
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        template="plotly_dark",
    )
    return fig

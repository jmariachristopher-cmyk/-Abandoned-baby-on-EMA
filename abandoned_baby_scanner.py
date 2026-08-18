"""
Abandoned Baby Scanner -- Command line / Tkinter desktop tool
================================================================

This is the local/desktop entry point. The actual pattern-detection engine
(tested independently) lives in scanner_core.py, which this file imports.
For a browser-based version with clickable buttons (deployable to Streamlit
Community Cloud straight from GitHub), see streamlit_app.py instead.

Usage:
    # Command line, pick the pattern with --pattern (the CLI "switch")
    python abandoned_baby_scanner.py --tickers RELIANCE TCS INFY --market NSE --pattern bullish
    python abandoned_baby_scanner.py --tickers AAPL MSFT NVDA --market US --pattern bearish
    python abandoned_baby_scanner.py --tickers-file tickers.txt --market NSE --pattern both

    # Desktop GUI with actual Bullish / Bearish / Both buttons (needs a display)
    python abandoned_baby_scanner.py --gui

    # Change timeframe (daily/weekly/monthly/intraday) and EMA length:
    python abandoned_baby_scanner.py --tickers AAPL --interval 1wk --ema-length 200 --period 5y
    python abandoned_baby_scanner.py --tickers AAPL --interval 1d  --ema-length 50  --period 1y
    python abandoned_baby_scanner.py --tickers AAPL --interval 1h  --ema-length 200 --period 720d

Configurable via CLI flags:
    --pattern      bullish, bearish, or both (default) -- the switch between the two patterns
    --gui          launch the desktop window with Bullish/Bearish/Both buttons instead of CLI
    --interval     Candle timeframe: 1d (default), 1wk, 1mo, or intraday 1h/30m/15m/5m etc.
    --ema-length   EMA period to use as the support/resistance filter (default 200; try 50, 21, ...)
    --period       How much history to pull -- must exceed --ema-length bars on that timeframe.
    --ema-tolerance, --doji-body-pct, --long-body-mult, --loose-gap  (pattern strictness knobs)

Notes:
    - Uses yfinance, so it needs internet access to Yahoo Finance when you run
      it on your own machine.
    - For NSE stocks, tickers need the ".NS" suffix (e.g. RELIANCE.NS). Pass
      --market NSE and give plain symbols (RELIANCE) and the script will add
      the suffix automatically.
"""

import argparse
import sys

from scanner_core import scan_tickers


# --------------------------------------------------------------------------
# Simple desktop GUI with Bullish / Bearish / Both buttons
# --------------------------------------------------------------------------

def launch_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, scrolledtext, messagebox
    except ImportError:
        print("Tkinter isn't available in this Python install. Run without --gui "
              "and use --pattern bullish/bearish/both from the command line instead.")
        return

    root = tk.Tk()
    root.title("Abandoned Baby Scanner")
    root.geometry("720x560")

    pattern_var = tk.StringVar(value="both")

    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="x")

    ttk.Label(frm, text="Tickers (space separated):").grid(row=0, column=0, sticky="w")
    tickers_entry = ttk.Entry(frm, width=50)
    tickers_entry.insert(0, "RELIANCE TCS INFY")
    tickers_entry.grid(row=0, column=1, columnspan=3, sticky="w", padx=5)

    ttk.Label(frm, text="Market:").grid(row=1, column=0, sticky="w")
    market_var = tk.StringVar(value="NSE")
    ttk.Combobox(frm, textvariable=market_var, values=["", "NSE", "US"], width=8,
                 state="readonly").grid(row=1, column=1, sticky="w", padx=5)

    ttk.Label(frm, text="Interval:").grid(row=1, column=2, sticky="w")
    interval_var = tk.StringVar(value="1d")
    ttk.Combobox(frm, textvariable=interval_var,
                 values=["1d", "1wk", "1mo", "1h", "30m", "15m", "5m"], width=8,
                 state="readonly").grid(row=1, column=3, sticky="w", padx=5)

    ttk.Label(frm, text="Period:").grid(row=2, column=0, sticky="w")
    period_entry = ttk.Entry(frm, width=10)
    period_entry.insert(0, "3y")
    period_entry.grid(row=2, column=1, sticky="w", padx=5)

    ttk.Label(frm, text="EMA length:").grid(row=2, column=2, sticky="w")
    ema_entry = ttk.Entry(frm, width=10)
    ema_entry.insert(0, "200")
    ema_entry.grid(row=2, column=3, sticky="w", padx=5)

    # --- the actual switch: Bullish / Bearish / Both buttons ---
    btn_frame = ttk.Frame(root, padding=(10, 0))
    btn_frame.pack(fill="x")
    ttk.Label(btn_frame, text="Pattern:").pack(side="left")

    def make_selector(value, text):
        b = ttk.Radiobutton(btn_frame, text=text, value=value, variable=pattern_var)
        b.pack(side="left", padx=8)
        return b

    make_selector("bullish", "Bullish Abandoned Baby")
    make_selector("bearish", "Bearish Abandoned Baby")
    make_selector("both", "Both")

    output = scrolledtext.ScrolledText(root, wrap="word")
    output.pack(fill="both", expand=True, padx=10, pady=10)

    def run_scan():
        tickers = tickers_entry.get().split()
        if not tickers:
            messagebox.showwarning("No tickers", "Enter at least one ticker.")
            return
        if market_var.get() == "NSE":
            tickers = [t if t.upper().endswith(".NS") else f"{t}.NS" for t in tickers]

        try:
            ema_length = int(ema_entry.get())
        except ValueError:
            messagebox.showerror("Invalid EMA length", "EMA length must be a whole number.")
            return

        output.delete("1.0", tk.END)
        output.insert(tk.END, f"Scanning {len(tickers)} ticker(s) for "
                               f"{pattern_var.get().upper()} pattern(s)...\n\n")
        root.update()

        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            results = scan_tickers(
                tickers,
                period=period_entry.get(),
                interval=interval_var.get(),
                ema_length=ema_length,
                pattern=pattern_var.get(),
            )
        output.insert(tk.END, buf.getvalue())

        output.insert(tk.END, "\n================ SUMMARY ================\n")
        if not results:
            output.insert(tk.END, f"No {pattern_var.get()} abandoned baby pattern(s) found.\n")
        else:
            for t, hits in results.items():
                output.insert(tk.END, f"\n{t}:\n")
                for h in hits:
                    arrow = "GREEN closes above RED" if h["pattern"] == "bullish" else "RED closes below GREEN"
                    output.insert(
                        tk.END,
                        f"  [{h['pattern'].upper()}] Day1 {h['day1_date'].date()} (open {h['day1_open']}) -> "
                        f"Day2 doji {h['day2_date'].date()} (close {h['day2_doji_close']}, "
                        f"EMA {h['ema_at_doji']}) -> "
                        f"Day3 {h['day3_date'].date()} (close {h['day3_close']}, {arrow})\n"
                    )
        output.see(tk.END)

    ttk.Button(btn_frame, text="Run Scan", command=run_scan).pack(side="right", padx=8)

    root.mainloop()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Bullish & Bearish Abandoned Baby scanner (EMA filtered)")
    ap.add_argument("--tickers", nargs="*", default=None, help="List of tickers, e.g. AAPL MSFT")
    ap.add_argument("--tickers-file", default=None, help="Text file, one ticker per line")
    ap.add_argument("--market", default="", choices=["", "NSE", "US"],
                     help="If NSE, plain symbols get '.NS' appended automatically")
    ap.add_argument("--period", default="3y",
                     help="History window to download, e.g. 6mo, 1y, 2y, 5y, max. "
                          "Must comfortably exceed --ema-length bars on the chosen --interval.")
    ap.add_argument("--interval", default="1d",
                     help="Candle timeframe: 1d (daily, default), 1wk (weekly), 1mo (monthly), "
                          "or intraday like 1h/30m/15m/5m (yfinance limits how far back intraday "
                          "data goes, so pair those with a short --period, e.g. --period 60d)")
    ap.add_argument("--ema-length", type=int, default=200,
                     help="EMA period/length to use as the support filter. Default 200. "
                          "Set to e.g. 50 or 21 to scan against a different EMA.")
    ap.add_argument("--pattern", default="both", choices=["bullish", "bearish", "both"],
                     help="Which pattern to scan for: bullish, bearish, or both (default). "
                          "This is the CLI equivalent of the switch/button in the GUI mode.")
    ap.add_argument("--gui", action="store_true",
                     help="Launch a small desktop window with Bullish/Bearish/Both buttons "
                          "instead of running from the command line.")
    ap.add_argument("--ema-tolerance", type=float, default=0.03,
                     help="How close (as a fraction) the doji must be to the EMA. Default 0.03 = 3%%")
    ap.add_argument("--doji-body-pct", type=float, default=0.10,
                     help="Max body size (as fraction of range) to count as a doji. Default 0.10")
    ap.add_argument("--long-body-mult", type=float, default=1.0,
                     help="Day1/Day3 body must be >= this x the 20-day average body. Default 1.0")
    ap.add_argument("--loose-gap", action="store_true",
                     help="Use body-only gaps instead of strict full-range island gaps")
    args = ap.parse_args()

    if args.gui:
        launch_gui()
        return

    tickers = list(args.tickers) if args.tickers else []
    if args.tickers_file:
        with open(args.tickers_file) as f:
            tickers += [line.strip() for line in f if line.strip()]

    if not tickers:
        print("No tickers given. Use --tickers or --tickers-file.")
        sys.exit(1)

    if args.market == "NSE":
        tickers = [t if t.upper().endswith(".NS") else f"{t}.NS" for t in tickers]

    results = scan_tickers(
        tickers,
        period=args.period,
        interval=args.interval,
        ema_length=args.ema_length,
        pattern=args.pattern,
        doji_body_pct=args.doji_body_pct,
        long_body_mult=args.long_body_mult,
        ema_tolerance_pct=args.ema_tolerance,
        strict_gap=not args.loose_gap,
    )

    print(f"\n================ SUMMARY (pattern={args.pattern}, interval={args.interval}, "
          f"EMA={args.ema_length}) ================")
    if not results:
        print(f"No {args.pattern} abandoned baby pattern(s) found near the {args.ema_length} EMA.")
    else:
        for t, hits in results.items():
            print(f"\n{t}:")
            for h in hits:
                arrow = "GREEN closes above RED" if h["pattern"] == "bullish" else "RED closes below GREEN"
                print(f"  [{h['pattern'].upper()}] Day1 {h['day1_date'].date()} (open {h['day1_open']}) -> "
                      f"Day2 doji {h['day2_date'].date()} (close {h['day2_doji_close']}, "
                      f"EMA{args.ema_length} {h['ema_at_doji']}) -> "
                      f"Day3 {h['day3_date'].date()} (close {h['day3_close']}, {arrow})")


if __name__ == "__main__":
    main()

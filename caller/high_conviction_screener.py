"""
high_conviction_screener.py — Personal-use screener that ONLY calls a setup
live if it already cleared backtest_engine.py's bar.

This is deliberately narrow. It will produce fewer calls than your existing
8-session bot — that's the point. A call here means: this exact pattern,
defined precisely enough to backtest, has a measured historical win rate
and positive expectancy over N years across the universe. Not a vibe, not
a probability formula nobody checked.

DEPENDENCY
----------
Requires backtest_results.json in the same folder, produced by running:
    python backtest_engine.py
Re-run the backtest periodically (monthly is reasonable) — an edge measured
in one market regime can fade in another. Nothing here monitors for that
automatically; that's a judgment call for you, not the script.

USAGE
-----
    python high_conviction_screener.py
"""

import json
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta

from backtest_engine import (
    SETUPS, UNIVERSE, rsi, macd_hist, ema,
)

IST = timezone(timedelta(hours=5, minutes=30))
RESULTS_FILE = "backtest_results.json"

# Position sizing — adjust to your actual account size
ACCOUNT_SIZE     = 100_000
RISK_PER_TRADE   = 0.02   # 2%


def load_validated_setups():
    """Returns dict of {setup_name: stats} for setups that passed the backtest."""
    path = Path(RESULTS_FILE)
    if not path.exists():
        print(f"❌ {RESULTS_FILE} not found. Run backtest_engine.py first — "
              f"this screener refuses to guess at what has edge.")
        return {}

    data   = json.loads(path.read_text())
    setups = data.get("setups", {})
    valid  = {k: v for k, v in setups.items() if v.get("verdict") == "VALIDATED"}

    run_at = data.get("run_at", "unknown")
    print(f"Backtest last run: {run_at}")
    print(f"Validated setups: {len(valid)}/{len(setups)}")
    for name, stats in valid.items():
        print(f"  {name}: n={stats['sample_size']}, "
              f"win rate={stats['win_rate']}%, "
              f"expectancy={stats['expectancy_pct']:+.2f}%")

    if not valid:
        print("\nNo validated setups — nothing will fire. This is correct "
              "behavior, not a bug. Widen the backtest universe/period and "
              "re-run, or accept that these particular setups don't have a "
              "measurable edge right now.")

    return valid


def scan_universe(validated_setups):
    """Checks today's data for each stock against each validated setup."""
    if not validated_setups:
        return []

    calls = []
    for sym in UNIVERSE:
        try:
            df = yf.download(sym, period="1y", interval="1d",
                             progress=False, auto_adjust=True)
            if df is None or len(df) < 250:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            close = df["Close"]
            price = float(close.iloc[-1])
            atr   = float((df["High"] - df["Low"]).rolling(14).mean().iloc[-1])

            for name in validated_setups:
                fn = SETUPS[name]
                fired = fn(df)
                if bool(fired.iloc[-1]):
                    stats = validated_setups[name]
                    risk_amount   = ACCOUNT_SIZE * RISK_PER_TRADE
                    stop_distance = atr
                    shares        = int(risk_amount / stop_distance) if stop_distance > 0 else 0

                    calls.append({
                        "symbol":       sym.replace(".NS", ""),
                        "setup":        name,
                        "price":        round(price, 2),
                        "stop":         round(price - atr, 2),
                        "target":       round(price + atr * 3, 2),
                        "shares":       shares,
                        "position_val": round(shares * price, 2),
                        "backtest_n":         stats["sample_size"],
                        "backtest_win_rate":  stats["win_rate"],
                        "backtest_expectancy": stats["expectancy_pct"],
                    })
        except Exception as e:
            print(f"  skipped {sym}: {e}")
            continue

    return calls


def format_call(c):
    return (
        f"📌 {c['symbol']} — {c['setup'].replace('_',' ').title()}\n"
        f"   Entry ₹{c['price']} | SL ₹{c['stop']} | Target ₹{c['target']} (1:3)\n"
        f"   Position: {c['shares']} shares (₹{c['position_val']:,.0f}) "
        f"at {int(RISK_PER_TRADE*100)}% account risk\n"
        f"   Backtest: {c['backtest_n']} instances, "
        f"{c['backtest_win_rate']}% win rate, "
        f"{c['backtest_expectancy']:+.2f}% expectancy/trade "
        f"(3y history, this universe)"
    )


def run():
    print(f"\n{'='*60}")
    print(f"HIGH CONVICTION SCREENER — {datetime.now(IST).strftime('%d %b %Y %H:%M IST')}")
    print("="*60 + "\n")

    validated = load_validated_setups()
    print()

    if not validated:
        return

    print("Scanning universe for live matches to validated setups...\n")
    calls = scan_universe(validated)

    print(f"\n{'='*60}")
    if not calls:
        print("No live matches today. This is the expected common case —")
        print("a validated setup with real edge still only fires occasionally.")
        print("Silence here means 'nothing met the bar,' not 'broken.'")
    else:
        print(f"{len(calls)} call(s) today:\n")
        for c in calls:
            print(format_call(c))
            print()
        print("⚠️  Education only. Not SEBI-registered advice. Use the stop loss.")
        print("⚠️  Backtest stats are historical, not a promise. Position size")
        print("    assumes ACCOUNT_SIZE at the top of this file — edit it to match")
        print("    your real capital before trusting the share counts.")
    print("="*60)


if __name__ == "__main__":
    run()

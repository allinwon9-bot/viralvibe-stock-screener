"""
backtest_engine.py — Measures whether a setup actually has historical edge
before it's allowed to generate a live call.

WHY THIS EXISTS
---------------
Every version of this bot so far has scored setups with a hand-tuned
"probability" formula (RSI weight 1.8, MACD weight 1.2, etc.) that was
never checked against what actually happened afterward. That's the
"illusion of control" — more indicators feels like more accuracy, but
nothing here was ever validated against history.

This module fixes that. For each setup definition, it scans N years of
daily data across a stock universe, finds every historical instance where
the setup fired, and measures the ACTUAL forward return distribution:
win rate, average win, average loss, expectancy, sample size.

Only setups that clear a minimum bar (sample size, win rate, positive
expectancy) are allowed into the live screener. Setups that don't clear
the bar are reported honestly as "no edge found" — that's a real and
useful outcome, not a failure of the script.

USAGE
-----
    python backtest_engine.py
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────
# UNIVERSE — Nifty 50 constituents. Widened from the original 20-stock set
# after that universe produced 0/4 validated setups, per the standard
# "widen universe/period and retest" path rather than loosening the bar.
#
# TATAMOTORS.NS delisted after Tata Motors' Oct 2025 demerger — the CV and
# PV/JLR businesses now trade as two separate companies. Both are included
# below (TMPV, TMCV) rather than guessing which one is the "real" successor.
# ─────────────────────────────────────────
UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "LT.NS", "BAJFINANCE.NS",
    "MARUTI.NS", "TITAN.NS", "SUNPHARMA.NS", "TATASTEEL.NS", "HINDALCO.NS",
    "ITC.NS", "HCLTECH.NS", "WIPRO.NS", "ASIANPAINT.NS", "ULTRACEMCO.NS",
    "BHARTIARTL.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "COALINDIA.NS",
    "NESTLEIND.NS", "BAJAJFINSV.NS", "M&M.NS", "TMPV.NS", "TMCV.NS", "ADANIENT.NS",
    "ADANIPORTS.NS", "JSWSTEEL.NS", "GRASIM.NS", "CIPLA.NS", "DRREDDY.NS",
    "APOLLOHOSP.NS", "DIVISLAB.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "BRITANNIA.NS",
    "TATACONSUM.NS", "SBILIFE.NS", "HDFCLIFE.NS", "BAJAJ-AUTO.NS", "INDUSINDBK.NS",
    "SHRIRAMFIN.NS", "TECHM.NS", "TRENT.NS", "BEL.NS", "UPL.NS",
]

BACKTEST_YEARS   = 3
FORWARD_DAYS     = 10      # measure return N trading days after signal
MIN_SAMPLE_SIZE  = 20      # need at least this many historical instances
MIN_WIN_RATE     = 0.55    # 55%+ of instances must have been profitable


# ─────────────────────────────────────────
# INDICATORS (same math as the live screener — must match exactly,
# or the backtest doesn't actually validate what goes live)
# ─────────────────────────────────────────
def rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = (-d.clip(upper=0)).rolling(p).mean()
    return 100 - (100 / (1 + g / (l + 1e-9)))

def macd_hist(s):
    m = s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()
    return m - m.ewm(span=9, adjust=False).mean()

def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def vol_ratio(vol, p=20):
    return vol / vol.rolling(p).mean()


# ─────────────────────────────────────────
# SETUP DEFINITIONS
# Each setup is a function: df -> boolean Series (True where setup fires)
# Keep these simple and nameable — a setup you can't explain in one
# sentence isn't one you should trust with real money.
# ─────────────────────────────────────────
def setup_rsi_pullback_in_uptrend(df):
    """RSI dips under 40 while price stays above EMA200 — pullback, not reversal."""
    r    = rsi(df["Close"])
    e200 = ema(df["Close"], 200)
    return (r < 40) & (df["Close"] > e200) & (r.shift(1) >= 40)

def setup_macd_cross_with_volume(df):
    """MACD histogram crosses positive alongside above-average volume."""
    h = macd_hist(df["Close"])
    v = vol_ratio(df["Volume"])
    crossed_up = (h > 0) & (h.shift(1) <= 0)
    return crossed_up & (v > 1.3)

def setup_golden_cross(df):
    """EMA50 crosses above EMA200, RSI not already overbought."""
    e50  = ema(df["Close"], 50)
    e200 = ema(df["Close"], 200)
    r    = rsi(df["Close"])
    crossed = (e50 > e200) & (e50.shift(1) <= e200.shift(1))
    return crossed & (r < 65)

def setup_oversold_bounce(df):
    """RSI under 30 (genuinely oversold) with a bullish day (close > open)."""
    r = rsi(df["Close"])
    return (r < 30) & (df["Close"] > df["Open"])


SETUPS = {
    "RSI_PULLBACK_UPTREND": setup_rsi_pullback_in_uptrend,
    "MACD_CROSS_VOLUME":    setup_macd_cross_with_volume,
    "GOLDEN_CROSS":         setup_golden_cross,
    "OVERSOLD_BOUNCE":      setup_oversold_bounce,
}


# ─────────────────────────────────────────
# BACKTEST CORE
# ─────────────────────────────────────────
def backtest_setup(setup_fn, universe=UNIVERSE, years=BACKTEST_YEARS,
                   forward_days=FORWARD_DAYS):
    """
    Returns list of forward returns (%) for every historical instance
    of this setup firing, across the whole universe.
    """
    all_returns = []
    period = f"{years}y"

    for sym in universe:
        try:
            df = yf.download(sym, period=period, interval="1d",
                             progress=False, auto_adjust=True)
            if df is None or len(df) < 250:
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            fired = setup_fn(df)
            close = df["Close"]

            fire_idx = np.where(fired.values)[0]
            for i in fire_idx:
                if i + forward_days >= len(close):
                    continue
                entry = float(close.iloc[i])
                exit_ = float(close.iloc[i + forward_days])
                if entry <= 0:
                    continue
                ret = ((exit_ - entry) / entry) * 100
                all_returns.append(ret)
        except Exception as e:
            print(f"    skipped {sym}: {e}")
            continue

    return all_returns


def summarize(returns, min_sample=MIN_SAMPLE_SIZE, min_win_rate=MIN_WIN_RATE):
    """Turns raw return list into a stats dict with a pass/fail verdict."""
    n = len(returns)
    if n == 0:
        return {"sample_size": 0, "verdict": "NO_INSTANCES"}

    arr      = np.array(returns)
    wins     = arr[arr > 0]
    losses   = arr[arr <= 0]
    win_rate = len(wins) / n
    avg_win  = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

    if n < min_sample:
        verdict = "INSUFFICIENT_SAMPLE"
    elif win_rate < min_win_rate:
        verdict = "NO_EDGE"
    elif expectancy <= 0:
        verdict = "NEGATIVE_EXPECTANCY"
    else:
        verdict = "VALIDATED"

    return {
        "sample_size": n,
        "win_rate":    round(win_rate * 100, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "expectancy_pct": round(expectancy, 2),
        "verdict":     verdict,
    }


def run_all_backtests(save_path="backtest_results.json"):
    print(f"Backtesting {len(SETUPS)} setups across {len(UNIVERSE)} stocks, "
          f"{BACKTEST_YEARS}y history, {FORWARD_DAYS}-day forward window\n")

    results = {}
    for name, fn in SETUPS.items():
        print(f"  Testing {name}...")
        returns = backtest_setup(fn)
        stats   = summarize(returns)
        results[name] = stats
        v = stats["verdict"]
        if v == "VALIDATED":
            print(f"    ✅ VALIDATED — n={stats['sample_size']}, "
                  f"win rate={stats['win_rate']}%, "
                  f"expectancy={stats['expectancy_pct']:+.2f}% per trade")
        elif v == "NO_INSTANCES":
            print(f"    ⚠️  No historical instances found in this universe/period")
        else:
            print(f"    ❌ {v} — n={stats.get('sample_size',0)}, "
                  f"win rate={stats.get('win_rate','?')}%")
        print()

    validated = [k for k, v in results.items() if v.get("verdict") == "VALIDATED"]
    print(f"Result: {len(validated)}/{len(SETUPS)} setups cleared the bar "
          f"(min {MIN_SAMPLE_SIZE} instances, {int(MIN_WIN_RATE*100)}%+ win rate, "
          f"positive expectancy).")
    if validated:
        print(f"Validated: {', '.join(validated)}")
    else:
        print("None validated on this universe/period — that's a real result, "
              "not a bug. The live screener will fire on nothing until a setup "
              "clears the bar, or until you widen the universe/period and retest.")

    output = {
        "run_at":        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "universe_size": len(UNIVERSE),
        "years":         BACKTEST_YEARS,
        "forward_days":  FORWARD_DAYS,
        "min_sample":    MIN_SAMPLE_SIZE,
        "min_win_rate":  MIN_WIN_RATE,
        "setups":        results,
    }
    Path(save_path).write_text(json.dumps(output, indent=2))
    print(f"\nSaved to {save_path} — the live screener reads this file and will "
          f"only fire on setups marked VALIDATED here.")

    return results


if __name__ == "__main__":
    run_all_backtests()

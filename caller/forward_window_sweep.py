"""
forward_window_sweep.py — Tests each setup at multiple forward-return
windows (5, 10, 20 days) instead of just the single 10-day window in
backtest_engine.py.

WHY THIS EXISTS
---------------
On the Nifty 50 / 3y run, MACD_CROSS_VOLUME (51.1%) and GOLDEN_CROSS (51.3%)
missed the 55% win-rate bar at a 10-day hold. A different holding period is
a legitimate different question ("does this setup work on a different exit
rule?"), not a threshold change. But testing 3 windows and only reporting
the one that happens to pass IS p-hacking — so this script reports all
windows for all setups, pass or fail, same as backtest_engine.py does for
a single window.

Reuses SETUPS, UNIVERSE, and summarize() from backtest_engine.py so the
indicator math and pass bar are identical — only forward_days changes.

USAGE
-----
    python forward_window_sweep.py
"""

import json
from pathlib import Path
from datetime import datetime

from backtest_engine import (
    SETUPS, UNIVERSE, BACKTEST_YEARS, MIN_SAMPLE_SIZE, MIN_WIN_RATE,
    backtest_setup, summarize,
)

FORWARD_WINDOWS = [5, 10, 20]


def run_sweep(save_path="forward_window_sweep.json"):
    print(f"Sweeping {len(SETUPS)} setups across {len(UNIVERSE)} stocks, "
          f"{BACKTEST_YEARS}y history, forward windows = {FORWARD_WINDOWS}\n")

    results = {}
    for name, fn in SETUPS.items():
        print(f"  {name}")
        results[name] = {}
        for fwd in FORWARD_WINDOWS:
            returns = backtest_setup(fn, forward_days=fwd)
            stats = summarize(returns)
            results[name][str(fwd)] = stats
            v = stats["verdict"]
            marker = "✅" if v == "VALIDATED" else "❌"
            print(f"    {fwd:>2}d — {marker} {v:<20} "
                  f"n={stats.get('sample_size', 0):<5} "
                  f"win rate={stats.get('win_rate', '?'):<6} "
                  f"expectancy={stats.get('expectancy_pct', '?')}")
        print()

    output = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "universe_size": len(UNIVERSE),
        "years": BACKTEST_YEARS,
        "forward_windows": FORWARD_WINDOWS,
        "min_sample": MIN_SAMPLE_SIZE,
        "min_win_rate": MIN_WIN_RATE,
        "setups": results,
    }
    Path(save_path).write_text(json.dumps(output, indent=2))
    print(f"Saved to {save_path}")

    return results


if __name__ == "__main__":
    run_sweep()

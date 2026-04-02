import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")
SESSION_LABEL      = os.getenv("SESSION_LABEL", "PRE_OPEN")
DATA_DIR           = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SESSION_ORDER = ["PRE_OPEN", "MARKET_OPEN", "BEST_TIME", "MIDDAY", "POWER_HOUR"]

SESSION_INFO = {
    "PRE_OPEN":    ("🕘 9:00 AM — PRE-OPEN",    "Market not open yet. Early signals only.\n⚡ Wait for 9:30 AM before entering any trade."),
    "MARKET_OPEN": ("🔔 9:15 AM — MARKET OPENS", "High volatility. Beginners wait till 9:30 AM.\nActive traders: watch for breakouts."),
    "BEST_TIME":   ("✅ 9:30 AM — BEST ENTRY",   "Initial volatility settled. Best time for beginners.\nTrends are clearer now. Risk is lower."),
    "MIDDAY":      ("☀️ 12:00 PM — MIDDAY",      "Low volatility. Good to review open positions.\nAvoid new entries unless strong breakout."),
    "POWER_HOUR":  ("⚡ 2:30 PM — POWER HOUR",   "Last hour. High liquidity returns.\n⚠️ Close ALL intraday positions before 3:20 PM!"),
}

# ─────────────────────────────────────────
# STOCK LISTS
# ─────────────────────────────────────────
NIFTY_50 = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS",
    "HINDUNILVR.NS","ITC.NS","SBIN.NS","BHARTIARTL.NS","KOTAKBANK.NS",
    "LT.NS","AXISBANK.NS","MARUTI.NS","TITAN.NS","BAJFINANCE.NS",
    "WIPRO.NS","TECHM.NS","SUNPHARMA.NS","POWERGRID.NS","ONGC.NS",
    "NTPC.NS","COALINDIA.NS","HINDALCO.NS","JSWSTEEL.NS","TATASTEEL.NS",
    "ADANIENT.NS","ADANIPORTS.NS","HCLTECH.NS","DRREDDY.NS","CIPLA.NS",
    "EICHERMOT.NS","HEROMOTOCO.NS","BAJAJ-AUTO.NS","TATAMOTORS.NS",
    "INDUSINDBK.NS","M&M.NS","BPCL.NS","APOLLOHOSP.NS","NESTLEIND.NS",
    "ULTRACEMCO.NS","ASIANPAINT.NS","BAJAJFINSV.NS","DIVISLAB.NS",
    "BRITANNIA.NS","GRASIM.NS","TATACONSUM.NS","UPL.NS","PIDILITIND.NS",
    "HDFCLIFE.NS","SBILIFE.NS"
]
BANK_NIFTY = [
    "HDFCBANK.NS","ICICIBANK.NS","KOTAKBANK.NS","SBIN.NS","AXISBANK.NS",
    "INDUSINDBK.NS","BANDHANBNK.NS","FEDERALBNK.NS","IDFCFIRSTB.NS",
    "PNB.NS","BANKBARODA.NS","AUBANK.NS"
]
MIDCAP_150 = [
    "MUTHOOTFIN.NS","PERSISTENT.NS","COFORGE.NS","LTTS.NS",
    "AUROPHARMA.NS","TORNTPHARM.NS","LUPIN.NS","BIOCON.NS",
    "VOLTAS.NS","HAVELLS.NS","POLYCAB.NS","DIXON.NS","CROMPTON.NS",
    "CHOLAFIN.NS","MANAPPURAM.NS","RECLTD.NS","PFC.NS","IRFC.NS",
    "NHPC.NS","IRCTC.NS","RVNL.NS","NLCINDIA.NS","SJVN.NS","PIIND.NS"
]
FNO_STOCKS = [
    "RELIANCE.NS","TCS.NS","INFY.NS","HDFCBANK.NS","ICICIBANK.NS",
    "SBIN.NS","AXISBANK.NS","BAJFINANCE.NS","LT.NS","TATAMOTORS.NS",
    "HINDALCO.NS","JSWSTEEL.NS","ONGC.NS","COALINDIA.NS","TECHM.NS",
    "ADANIENT.NS","ADANIPORTS.NS","WIPRO.NS","INDIGO.NS","HCLTECH.NS"
]

ALL_STOCKS = list(set(NIFTY_50 + BANK_NIFTY + MIDCAP_150 + FNO_STOCKS))
ALL_STOCKS = [s for s in ALL_STOCKS if ".NS" in s]

# ─────────────────────────────────────────
# SENTIMENT
# ─────────────────────────────────────────
BULLISH_WORDS = [
    "rally","surge","gain","rise","jump","soar","bullish","recovery",
    "rebound","positive","growth","profit","strong","buy","upgrade",
    "beat","record","high","boom","optimism","rate cut","fii buying",
    "dii buying","green","breakout","momentum","stimulus"
]
BEARISH_WORDS = [
    "fall","drop","decline","crash","sell","bearish","weak","loss",
    "negative","risk","fear","war","tension","inflation","rate hike",
    "fii selling","outflow","red","breakdown","correction","plunge",
    "concern","pressure","slowdown","deficit","recession"
]

def fetch_sentiment():
    feeds = [
        "https://news.google.com/rss/search?q=NSE+Nifty+stock+market+India&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Sensex+BSE+India+market+today&hl=en-IN&gl=IN&ceid=IN:en",
    ]
    headlines = []
    for url in feeds:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:10]:
                t = item.find("title")
                if t is not None and t.text:
                    headlines.append(t.text.lower())
        except Exception as e:
            print(f"News error: {e}")

    if not headlines:
        return 0, [], "NEUTRAL"

    bull = bear = 0
    matched = []
    for h in headlines:
        b  = sum(1 for w in BULLISH_WORDS if w in h)
        br = sum(1 for w in BEARISH_WORDS if w in h)
        if b > br:
            bull += b
            matched.append(("🟢", h[:75]))
        elif br > b:
            bear += br
            matched.append(("🔴", h[:75]))
        else:
            matched.append(("⚪", h[:75]))

    total = bull + bear
    if total == 0:
        return 0, matched[:4], "NEUTRAL"

    score = round(((bull - bear) / total) * 100)
    if score >= 40:    mood = "STRONGLY BULLISH"
    elif score >= 15:  mood = "BULLISH"
    elif score <= -40: mood = "STRONGLY BEARISH"
    elif score <= -15: mood = "BEARISH"
    else:              mood = "NEUTRAL"

    return score, matched[:4], mood

# ─────────────────────────────────────────
# INDICATORS
# ─────────────────────────────────────────
def rsi(series, p=14):
    d = series.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = (-d.clip(upper=0)).rolling(p).mean()
    return 100 - (100 / (1 + g / (l + 1e-9)))

def macd_hist(series):
    e12 = series.ewm(span=12, adjust=False).mean()
    e26 = series.ewm(span=26, adjust=False).mean()
    m   = e12 - e26
    s   = m.ewm(span=9, adjust=False).mean()
    return m - s

def ema(series, p):
    return series.ewm(span=p, adjust=False).mean()

def vol_spike(vol, p=20):
    avg = vol.rolling(p).mean()
    return float(vol.iloc[-1]) > float(avg.iloc[-1]) * 1.5

# ─────────────────────────────────────────
# PROBABILITY
# ─────────────────────────────────────────
def calc_prob(rsi_val, hist_val, price, e50, e200, spike, direction, sentiment):
    score = 0
    if direction == "BULLISH":
        if rsi_val < 30:        score += 1.8
        elif rsi_val < 40:      score += 1.0
        elif rsi_val < 50:      score += 0.5
        if hist_val > 0:        score += 1.2
        if price > e50:         score += 0.8
        if price > e200:        score += 1.0
        if spike:               score += 0.5
        if sentiment > 30:      score += 0.7
        elif sentiment > 0:     score += 0.3
    else:
        if rsi_val > 70:        score += 1.8
        elif rsi_val > 60:      score += 1.0
        elif rsi_val > 50:      score += 0.5
        if hist_val < 0:        score += 1.2
        if price < e50:         score += 0.8
        if price < e200:        score += 1.0
        if spike:               score += 0.5
        if sentiment < -30:     score += 0.7
        elif sentiment < 0:     score += 0.3
    return min(round((score / 6.0) * 100), 97)

# ─────────────────────────────────────────
# ANALYZE ONE STOCK
# ─────────────────────────────────────────
def analyze(symbol, sentiment):
    try:
        df = yf.download(symbol, period="6mo", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 50:
            return None

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()
        price  = float(close.iloc[-1])

        r      = float(rsi(close).iloc[-1])
        h      = macd_hist(close)
        hval   = float(h.iloc[-1])
        hprev  = float(h.iloc[-2])
        e50    = float(ema(close, 50).iloc[-1])
        e200   = float(ema(close, 200).iloc[-1])
        spike  = vol_spike(volume)
        cross  = (hval > 0 and hprev <= 0) or (hval < 0 and hprev >= 0)

        bp = calc_prob(r, hval, price, e50, e200, spike, "BULLISH", sentiment)
        sp = calc_prob(r, hval, price, e50, e200, spike, "BEARISH", sentiment)

        atr = float((df["High"] - df["Low"]).squeeze().rolling(14).mean().iloc[-1])

        if bp >= 60 and bp > sp:
            direction = "BULLISH"
            prob      = bp
            entry     = round(price, 2)
            target    = round(price + atr * 2, 2)
            sl        = round(price - atr, 2)
        elif sp >= 60 and sp > bp:
            direction = "BEARISH"
            prob      = sp
            entry     = round(price, 2)
            target    = round(price - atr * 2, 2)
            sl        = round(price + atr, 2)
        else:
            return None

        return {
            "symbol":    symbol.replace(".NS", ""),
            "direction": direction,
            "prob":      prob,
            "entry":     entry,
            "target":    target,
            "sl":        sl,
            "rsi":       round(r, 1),
            "vol_spike": spike,
            "cross":     cross,
        }
    except Exception as e:
        print(f"  Error {symbol}: {e}")
        return None

# ─────────────────────────────────────────
# SCREEN ALL
# ─────────────────────────────────────────
def screen(sentiment):
    print(f"Screening {len(ALL_STOCKS)} stocks...")
    results = []
    for sym in ALL_STOCKS:
        r = analyze(sym, sentiment)
        if r:
            results.append(r)

    bullish = sorted([r for r in results if r["direction"] == "BULLISH"],
                     key=lambda x: x["prob"], reverse=True)[:5]
    bearish = sorted([r for r in results if r["direction"] == "BEARISH"],
                     key=lambda x: x["prob"], reverse=True)[:5]
    return bullish, bearish

# ─────────────────────────────────────────
# SAVE SESSION DATA TO FILE
# ─────────────────────────────────────────
def save_session(label, bullish, bearish, sentiment_score, mood):
    today = datetime.now().strftime("%Y-%m-%d")
    data  = {
        "session":   label,
        "date":      today,
        "time":      datetime.now().strftime("%H:%M"),
        "sentiment": sentiment_score,
        "mood":      mood,
        "bullish":   bullish,
        "bearish":   bearish,
    }
    path = DATA_DIR / f"session_{label}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✅ Saved {path}")

# ─────────────────────────────────────────
# LOAD ALL PREVIOUS SESSIONS
# ─────────────────────────────────────────
def load_all_sessions():
    sessions = {}
    today = datetime.now().strftime("%Y-%m-%d")
    for label in SESSION_ORDER[:-1]:  # exclude POWER_HOUR
        path = DATA_DIR / f"session_{label}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            if data.get("date") == today:
                sessions[label] = data
    return sessions

# ─────────────────────────────────────────
# BUILD SCORECARD FOR POWER HOUR
# ─────────────────────────────────────────
def build_scorecard(sessions):
    """
    For each stock that appeared in any session,
    track how many sessions it appeared in and direction.
    Returns confirmed_bullish, confirmed_bearish, partial, conflicting
    """
    # stock -> {session_label: direction, prob}
    tracker = {}

    for label, data in sessions.items():
        for s in data.get("bullish", []):
            sym = s["symbol"]
            if sym not in tracker:
                tracker[sym] = {"sessions": {}, "entries": [], "targets": [], "sls": []}
            tracker[sym]["sessions"][label] = "BULLISH"
            tracker[sym]["entries"].append(s["entry"])
            tracker[sym]["targets"].append(s["target"])
            tracker[sym]["sls"].append(s["sl"])
            tracker[sym]["last_prob"] = s["prob"]

        for s in data.get("bearish", []):
            sym = s["symbol"]
            if sym not in tracker:
                tracker[sym] = {"sessions": {}, "entries": [], "targets": [], "sls": []}
            tracker[sym]["sessions"][label] = "BEARISH"
            tracker[sym]["entries"].append(s["entry"])
            tracker[sym]["targets"].append(s["target"])
            tracker[sym]["sls"].append(s["sl"])
            tracker[sym]["last_prob"] = s["prob"]

    total_sessions = len(sessions)
    confirmed_bull = []
    confirmed_bear = []
    partial        = []
    conflicting    = []

    for sym, info in tracker.items():
        sess       = info["sessions"]
        directions = list(sess.values())
        count      = len(directions)
        bull_count = directions.count("BULLISH")
        bear_count = directions.count("BEARISH")

        # build session dots
        dots = ""
        for label in SESSION_ORDER[:-1]:
            if label in sess:
                dots += "🟢" if sess[label] == "BULLISH" else "🔴"
            else:
                dots += "⚪"

        avg_entry  = round(sum(info["entries"]) / len(info["entries"]), 2)
        avg_target = round(sum(info["targets"]) / len(info["targets"]), 2)
        avg_sl     = round(sum(info["sls"])     / len(info["sls"]),     2)
        prob       = info.get("last_prob", 0)

        item = {
            "symbol":  sym,
            "dots":    dots,
            "count":   count,
            "total":   total_sessions,
            "prob":    prob,
            "entry":   avg_entry,
            "target":  avg_target,
            "sl":      avg_sl,
        }

        if bull_count > 0 and bear_count > 0:
            conflicting.append(item)           # mixed signals
        elif count == total_sessions:
            if bull_count == total_sessions:
                confirmed_bull.append(item)    # 4/4 bullish
            else:
                confirmed_bear.append(item)    # 4/4 bearish
        elif count >= 2:
            item["direction"] = "BULLISH" if bull_count > bear_count else "BEARISH"
            partial.append(item)               # 2/4 or 3/4

    # sort by count desc then prob desc
    confirmed_bull.sort(key=lambda x: (x["count"], x["prob"]), reverse=True)
    confirmed_bear.sort(key=lambda x: (x["count"], x["prob"]), reverse=True)
    partial.sort(key=lambda x: (x["count"], x["prob"]), reverse=True)

    return confirmed_bull, confirmed_bear, partial[:4], conflicting[:4]

# ─────────────────────────────────────────
# FORMAT REGULAR SESSION MESSAGE
# ─────────────────────────────────────────
def format_regular(label, bullish, bearish, sentiment_score, mood, headlines):
    title, advice = SESSION_INFO[label]
    now = datetime.now().strftime("%d %b %Y | %I:%M %p")

    lvl  = abs(sentiment_score) // 20
    bar  = ("🟢" if sentiment_score >= 0 else "🔴") * min(lvl, 5)
    bar += "⬜" * (5 - min(lvl, 5))

    lines = [
        f"*{title}*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n📰 *SENTIMENT: {mood}*",
        f"{bar}  {sentiment_score:+d}/100",
    ]

    if headlines:
        lines.append("")
        for icon, h in headlines[:3]:
            lines.append(f"{icon} _{h}_")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ *TIMING TIP*\n{advice}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    def fmt_calls(calls, direction):
        icon = "🟢" if direction == "BULLISH" else "🔴"
        action = "BUY" if direction == "BULLISH" else "SELL"
        if not calls:
            return [f"\n{icon} No strong {direction.lower()} calls right now"]
        out = [f"\n{icon} *{direction} CALLS*"]
        for i, s in enumerate(calls, 1):
            tags = []
            if s.get("vol_spike"): tags.append("🔥Vol")
            if s.get("cross"):     tags.append("⚡MACD")
            rr_val = abs(s["target"] - s["entry"])
            rr_risk = abs(s["sl"] - s["entry"])
            rr = f"{round(rr_val/rr_risk,1)}:1" if rr_risk > 0 else "-"
            out.append(
                f"\n{i}. *{s['symbol']}* → {action} {' '.join(tags)}\n"
                f"   📊 `{s['prob']}% {direction.lower()}`  |  RSI: {s['rsi']}  |  R:R {rr}\n"
                f"   Entry ₹{s['entry']}  🎯 ₹{s['target']}  🛑 ₹{s['sl']}"
            )
        return out

    lines += fmt_calls(bullish, "BULLISH")
    lines += fmt_calls(bearish, "BEARISH")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _Education only. Always use stop loss._",
        "🤖 _ViralVibe Stock Bot_"
    ]
    return "\n".join(lines)

# ─────────────────────────────────────────
# FORMAT POWER HOUR SCORECARD
# ─────────────────────────────────────────
def format_scorecard(confirmed_bull, confirmed_bear, partial, conflicting,
                     current_bull, current_bear, sentiment_score, mood, headlines):
    now = datetime.now().strftime("%d %b %Y | %I:%M %p")

    lvl = abs(sentiment_score) // 20
    bar = ("🟢" if sentiment_score >= 0 else "🔴") * min(lvl, 5)
    bar += "⬜" * (5 - min(lvl, 5))

    lines = [
        "⚡ *POWER HOUR — FULL DAY SCORECARD*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📰 *SENTIMENT: {mood}*  {bar}  {sentiment_score:+d}/100",
        "\n_Sessions: PRE-OPEN | OPEN | 9:30 | MIDDAY_",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # confirmed bullish
    if confirmed_bull:
        lines.append("\n🏆 *CONFIRMED BUY — All sessions agreed*")
        for s in confirmed_bull:
            lines.append(
                f"\n✅ *{s['symbol']}*  {s['dots']}  ({s['count']}/{s['total']} sessions)\n"
                f"   📊 Prob: `{s['prob']}%`\n"
                f"   Entry ₹{s['entry']}  🎯 ₹{s['target']}  🛑 ₹{s['sl']}"
            )
    else:
        lines.append("\n🏆 No stocks confirmed bullish across all sessions today")

    # confirmed bearish
    if confirmed_bear:
        lines.append("\n🏆 *CONFIRMED SELL — All sessions agreed*")
        for s in confirmed_bear:
            lines.append(
                f"\n✅ *{s['symbol']}*  {s['dots']}  ({s['count']}/{s['total']} sessions)\n"
                f"   📊 Prob: `{s['prob']}%`\n"
                f"   Entry ₹{s['entry']}  🎯 ₹{s['target']}  🛑 ₹{s['sl']}"
            )
    else:
        lines.append("\n🏆 No stocks confirmed bearish across all sessions today")

    # partial
    if partial:
        lines.append("\n⚠️ *PARTIAL SIGNALS — Use smaller quantity*")
        for s in partial:
            icon = "🟢" if s.get("direction") == "BULLISH" else "🔴"
            lines.append(f"  {icon} *{s['symbol']}*  {s['dots']}  ({s['count']}/{s['total']})  `{s['prob']}%`")

    # conflicting
    if conflicting:
        lines.append("\n❌ *SKIP THESE — Conflicting signals*")
        for s in conflicting:
            lines.append(f"  ⚠️ *{s['symbol']}*  {s['dots']}  Mixed direction")

    # current session calls
    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📊 *CURRENT 2:30 PM SCAN*",
    ]
    if current_bull:
        lines.append("🟢 Fresh Bullish:")
        for s in current_bull:
            lines.append(f"  • *{s['symbol']}* `{s['prob']}%`  Entry ₹{s['entry']}  🎯 ₹{s['target']}  🛑 ₹{s['sl']}")
    if current_bear:
        lines.append("🔴 Fresh Bearish:")
        for s in current_bear:
            lines.append(f"  • *{s['symbol']}* `{s['prob']}%`  Entry ₹{s['entry']}  🎯 ₹{s['target']}  🛑 ₹{s['sl']}")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🚨 *REMINDER: Square off ALL intraday positions before 3:20 PM!*",
        "⚠️ _Education only. Always use stop loss._",
        "🤖 _ViralVibe Stock Bot_"
    ]
    return "\n".join(lines)

# ─────────────────────────────────────────
# SEND TELEGRAM
# ─────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  No Telegram credentials. Printing message:\n")
        print(message)
        return
    url  = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=15)
        if r.status_code == 200:
            print("✅ Sent to Telegram!")
        else:
            print(f"❌ Telegram error {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Failed: {e}")

# ─────────────────────────────────────────
# CLEAR OLD DATA (cleanup previous day)
# ─────────────────────────────────────────
def clear_old_data():
    today = datetime.now().strftime("%Y-%m-%d")
    for path in DATA_DIR.glob("session_*.json"):
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("date") != today:
                path.unlink()
                print(f"🗑️  Cleared old file: {path.name}")
        except Exception:
            path.unlink()

# ─────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────
def run():
    print(f"\n{'='*45}")
    print(f"SESSION: {SESSION_LABEL}  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*45)

    # cleanup old day files
    clear_old_data()

    # Step 1: News sentiment
    print("📰 Fetching sentiment...")
    sentiment_score, headlines, mood = fetch_sentiment()
    print(f"   → {mood} ({sentiment_score:+d})")

    # Step 2: Screen stocks
    print("📊 Screening stocks...")
    bullish, bearish = screen(sentiment_score)
    print(f"   → {len(bullish)} bullish, {len(bearish)} bearish")

    if SESSION_LABEL == "POWER_HOUR":
        # Step 3a: Load all previous sessions
        print("📂 Loading previous sessions...")
        sessions = load_all_sessions()
        print(f"   → Found {len(sessions)} previous sessions: {list(sessions.keys())}")

        # Step 3b: Build scorecard
        confirmed_bull, confirmed_bear, partial, conflicting = build_scorecard(sessions)

        # Step 3c: Format and send scorecard
        msg = format_scorecard(
            confirmed_bull, confirmed_bear, partial, conflicting,
            bullish, bearish, sentiment_score, mood, headlines
        )
    else:
        # Step 3a: Save this session's data
        save_session(SESSION_LABEL, bullish, bearish, sentiment_score, mood)

        # Step 3b: Format regular message
        msg = format_regular(SESSION_LABEL, bullish, bearish,
                             sentiment_score, mood, headlines)

    # Step 4: Send to Telegram
    send_telegram(msg)
    print("Done!")

# ─────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────
if __name__ == "__main__":
    run()

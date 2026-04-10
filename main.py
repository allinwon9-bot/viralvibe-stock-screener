import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from nse_data import (
    get_nse_snapshot,
    format_fii_dii_summary,
    format_indices_summary,
    get_upcoming_holidays,
)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY",  "")
SESSION_LABEL      = os.getenv("SESSION_LABEL", "MORNING_BRIEFING")

IST      = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Sessions that save data for EOD scorecard
TRACKING_SESSIONS = ["BEST_ENTRY", "MIDDAY_REVIEW", "POWER_HOUR_PREP", "CLOSING_ANALYSIS"]

# ─────────────────────────────────────────
# SESSION DEFINITIONS
# Each session has: title, emoji, tip, prompt_focus, do_screen
# ─────────────────────────────────────────
SESSIONS = {

    "MORNING_BRIEFING": {
        "title":    "☀️ 8:00 AM — MORNING BRIEFING",
        "tip":      "Market opens in 1 hour. Prepare your watchlist now.",
        "focus":    """Focus on:
1. Overnight global market movements (US close, Asian open)
2. FII/DII activity from yesterday
3. Key events today (RBI, earnings, macro data)
4. Suggested watchlist of 3-4 stocks to track today
5. Overall market mood for the day
Do NOT give specific entry/exit levels yet — market not open.""",
        "do_screen": False,
        "do_stock_calls": False,
    },

    "PRE_OPEN": {
        "title":    "🕘 9:00 AM — PRE-OPEN ANALYSIS",
        "tip":      "Pre-open session running. Watch order book for direction.",
        "focus":    """Focus on:
1. Pre-open order book signals (gap up/gap down expected)
2. SGX Nifty / GIFT Nifty indication
3. Key stocks showing large buy/sell orders
4. Initial bias: gap up or gap down expected?
5. Stocks to watch at open
Keep it brief — only 15 minutes before market opens.""",
        "do_screen": False,
        "do_stock_calls": True,
    },

    "MARKET_OPEN": {
        "title":    "🔔 9:15 AM — MARKET OPEN",
        "tip":      "Highly volatile! Beginners avoid first 15 minutes.",
        "focus":    """Focus on:
1. Opening move — gap up/gap down confirmed
2. Which sectors leading the open
3. High momentum breakout stocks RIGHT NOW
4. Any opening surprises vs pre-open expectation
5. Quick scalp opportunities (tight SL, quick target)
Be very precise — this is fast money window.""",
        "do_screen": True,
        "do_stock_calls": True,
    },

    "BEST_ENTRY": {
        "title":    "✅ 9:30 AM — BEST ENTRY WINDOW",
        "tip":      "Volatility settling. Best risk-reward window for beginners.",
        "focus":    """Focus on:
1. Confirmed trend direction after opening volatility
2. Best 3 stocks for intraday with clear entry/SL/target
3. Nifty support/resistance for the day
4. Stocks showing volume + price confirmation
5. Ideal position sizing suggestion
This is the PRIMARY trading window — be most detailed here.""",
        "do_screen": True,
        "do_stock_calls": True,
    },

    "MIDDAY_REVIEW": {
        "title":    "☀️ 12:00 PM — MIDDAY REVIEW",
        "tip":      "Low volume period. Review open positions. Avoid new entries.",
        "focus":    """Focus on:
1. How morning calls performed — hit target/SL?
2. Current Nifty position vs morning prediction
3. Any news/events since morning that changed outlook
4. Stocks consolidating for afternoon breakout
5. Position management advice for open trades
Review and adjust — not a new entry window.""",
        "do_screen": True,
        "do_stock_calls": True,
    },

    "POWER_HOUR_PREP": {
        "title":    "⚡ 2:00 PM — POWER HOUR PREP",
        "tip":      "Last 90 minutes. High liquidity returning. Best momentum trades.",
        "focus":    """Focus on:
1. Setup for last 90 minutes of trading
2. Stocks showing afternoon momentum building
3. F&O data — Put/Call ratio, max pain level
4. Whether to hold morning positions or book profit
5. Best 2-3 momentum trades for 2-3:15 PM window
Remember: square off by 3:20 PM for intraday!""",
        "do_screen": True,
        "do_stock_calls": True,
    },

    "CLOSING_ANALYSIS": {
        "title":    "🔔 3:00 PM — CLOSING ANALYSIS",
        "tip":      "⚠️ 20 minutes left! Close ALL intraday positions by 3:20 PM!",
        "focus":    """Focus on:
1. URGENT: Remind to close intraday positions before 3:20 PM
2. Final 30 minutes market direction
3. Any last-minute delivery buys worth holding overnight?
4. Today's key market lesson / takeaway
5. Preview of tomorrow — what to watch
Be very direct about closing positions — safety first!""",
        "do_screen": False,
        "do_stock_calls": False,
    },

    "EOD_SCORECARD": {
        "title":    "📊 3:30 PM — END OF DAY SCORECARD",
        "tip":      "Market closed. Review the full day performance.",
        "focus":    """Focus on:
1. Full day summary — Nifty/Sensex/BankNifty final close
2. How the day's bias prediction was right/wrong
3. Which trade setups worked and which failed
4. Key stocks performance today
5. Tomorrow's outlook — what to prepare for
6. Any overnight positions worth considering
Be honest about accuracy — builds trust with readers.""",
        "do_screen": False,
        "do_stock_calls": False,
    },
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
# NEWS FETCHER
# ─────────────────────────────────────────
def fetch_headlines(session):
    # Different feeds for different sessions
    feeds_map = {
        "MORNING_BRIEFING": [
            "https://news.google.com/rss/search?q=US+market+overnight+Asia+market+India&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=NSE+Nifty+India+stock+market+today&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=RBI+crude+oil+rupee+India+economy&hl=en-IN&gl=IN&ceid=IN:en",
        ],
        "EOD_SCORECARD": [
            "https://news.google.com/rss/search?q=Sensex+Nifty+close+today+India&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=India+stock+market+close+analysis&hl=en-IN&gl=IN&ceid=IN:en",
        ],
        "DEFAULT": [
            "https://news.google.com/rss/search?q=NSE+Nifty+Sensex+India+stock+market+today&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=FII+DII+India+market&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=global+cues+crude+oil+rupee+India&hl=en-IN&gl=IN&ceid=IN:en",
        ],
    }

    feeds = feeds_map.get(session, feeds_map["DEFAULT"])
    all_h = []
    for url in feeds:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:8]:
                t = item.find("title")
                if t is not None and t.text:
                    all_h.append(t.text.strip())
        except Exception as e:
            print(f"  News error: {e}")

    seen, unique = set(), []
    for h in all_h:
        if h.lower() not in seen:
            seen.add(h.lower())
            unique.append(h)
    print(f"  Fetched {len(unique)} headlines")
    return unique[:18]

# ─────────────────────────────────────────
# TECHNICAL SCREENER
# ─────────────────────────────────────────
def rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = (-d.clip(upper=0)).rolling(p).mean()
    return 100 - (100 / (1 + g / (l + 1e-9)))

def macd_hist(s):
    m = s.ewm(span=12,adjust=False).mean() - s.ewm(span=26,adjust=False).mean()
    return m - m.ewm(span=9,adjust=False).mean()

def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def vol_spike(vol, p=20):
    return float(vol.iloc[-1]) > float(vol.rolling(p).mean().iloc[-1]) * 1.5

def calc_prob(rv, hv, price, e50, e200, spike, direction):
    sc = 0
    if direction == "BULLISH":
        if rv < 30: sc+=1.8
        elif rv < 40: sc+=1.0
        elif rv < 50: sc+=0.5
        if hv > 0: sc+=1.2
        if price > e50: sc+=0.8
        if price > e200: sc+=1.0
        if spike: sc+=0.5
    else:
        if rv > 70: sc+=1.8
        elif rv > 60: sc+=1.0
        elif rv > 50: sc+=0.5
        if hv < 0: sc+=1.2
        if price < e50: sc+=0.8
        if price < e200: sc+=1.0
        if spike: sc+=0.5
    return min(round((sc / 5.5) * 100), 97)

def analyze_stock(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 50: return None
        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()
        price  = float(close.iloc[-1])
        rv     = float(rsi(close).iloc[-1])
        h      = macd_hist(close)
        hv     = float(h.iloc[-1])
        hp     = float(h.iloc[-2])
        e50    = float(ema(close,50).iloc[-1])
        e200   = float(ema(close,200).iloc[-1])
        spike  = vol_spike(volume)
        cross  = (hv>0 and hp<=0) or (hv<0 and hp>=0)
        atr    = float((df["High"]-df["Low"]).squeeze().rolling(14).mean().iloc[-1])
        bp = calc_prob(rv, hv, price, e50, e200, spike, "BULLISH")
        sp = calc_prob(rv, hv, price, e50, e200, spike, "BEARISH")
        if bp >= 50 and bp > sp:
            return {"symbol":symbol.replace(".NS",""),"direction":"BULLISH",
                    "prob":bp,"entry":round(price,2),"target":round(price+atr*2,2),
                    "sl":round(price-atr,2),"rsi":round(rv,1),"vol_spike":spike,"cross":cross}
        elif sp >= 50 and sp > bp:
            return {"symbol":symbol.replace(".NS",""),"direction":"BEARISH",
                    "prob":sp,"entry":round(price,2),"target":round(price-atr*2,2),
                    "sl":round(price+atr,2),"rsi":round(rv,1),"vol_spike":spike,"cross":cross}
        return None
    except Exception as e:
        print(f"  Error {symbol}: {e}")
        return None

def screen_stocks():
    print(f"  Downloading all stocks at once...")
    try:
        # Download all at once — much faster, less rate limiting
        symbols_str = " ".join(ALL_STOCKS)
        all_data = yf.download(
            symbols_str,
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            timeout=60
        )
        print(f"  ✅ Batch download complete")
    except Exception as e:
        print(f"  Batch download failed: {e}, falling back to individual")
        all_data = None
    # ... rest of analysis
# ─────────────────────────────────────────
# CLAUDE AI ANALYSIS
# ─────────────────────────────────────────
def get_claude_analysis(session, headlines, nse_snapshot, bullish, bearish):
    if not ANTHROPIC_API_KEY:
        return None

    sess_config = SESSIONS[session]
    today       = datetime.now(IST).strftime("%d %b %Y %A")
    time_now    = datetime.now(IST).strftime("%I:%M %p")
    indices_str = format_indices_summary(nse_snapshot.get("indices", {}))
    fii_str     = format_fii_dii_summary(nse_snapshot.get("fii_dii", []))
    movers      = nse_snapshot.get("movers", {})
    gainers     = ", ".join([f"{g['symbol']}(+{g['change']}%)" for g in movers.get("gainers",[])[:3]])
    losers      = ", ".join([f"{l['symbol']}({l['change']}%)" for l in movers.get("losers",[])[:3]])
    upcoming    = nse_snapshot.get("upcoming", [])
    upcoming_str= ", ".join([f"{h['description']}({h['display']})" for h in upcoming[:2]]) or "None"

    bull_str = "\n".join([f"  {s['symbol']}: RSI {s['rsi']} Prob {s['prob']}% Entry ₹{s['entry']} T ₹{s['target']} SL ₹{s['sl']}" for s in bullish[:3]]) or "None"
    bear_str = "\n".join([f"  {s['symbol']}: RSI {s['rsi']} Prob {s['prob']}% Entry ₹{s['entry']} T ₹{s['target']} SL ₹{s['sl']}" for s in bearish[:3]]) or "None"
    news_str = "\n".join([f"  - {h}" for h in headlines[:15]])

    # Load previous sessions for context
    prev_context = ""
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    for label in TRACKING_SESSIONS:
        path = DATA_DIR / f"session_{label}.json"
        if path.exists():
            try:
                with open(path) as f:
                    d = json.load(f)
                if d.get("date") == today_str:
                    prev_context += f"\n{label} had {len(d.get('bullish',[]))} bullish, {len(d.get('bearish',[]))} bearish calls"
            except Exception:
                pass

    prompt = f"""You are a senior professional Indian stock market analyst writing for retail traders.
Today: {today} | Current time: {time_now} IST | Session: {session}

NSE LIVE DATA:
{indices_str}

FII/DII:
{fii_str}

TOP GAINERS: {gainers or 'N/A'}
TOP LOSERS: {losers or 'N/A'}
UPCOMING HOLIDAYS: {upcoming_str}
PREVIOUS SESSIONS TODAY: {prev_context or 'First session of day'}

LATEST NEWS:
{news_str}

TECHNICAL SCREENER:
Bullish:
{bull_str}
Bearish:
{bear_str}

SESSION FOCUS — {session}:
{sess_config['focus']}

Write a professional analysis following the session focus above.
Use plain text. No markdown. Use these exact section headers on separate lines.
Keep total under 500 words. Be specific with price levels.
End with one line: CONFIDENCE: [HIGH/MEDIUM/LOW] | BIAS: [BULLISH/BEARISH/SIDEWAYS]"""

    try:
        print("  Calling Claude AI...")
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001",
                  "max_tokens": 1100,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30
        )
        if res.status_code == 200:
            print("  ✅ Claude done")
            return res.json()["content"][0]["text"]
        print(f"  ❌ Claude error: {res.status_code}")
        return None
    except Exception as e:
        print(f"  ❌ Claude failed: {e}")
        return None

# ─────────────────────────────────────────
# SESSION SCORECARD (EOD)
# ─────────────────────────────────────────
def load_all_sessions():
    today, sessions = datetime.now(IST).strftime("%Y-%m-%d"), {}
    for label in TRACKING_SESSIONS:
        path = DATA_DIR / f"session_{label}.json"
        if path.exists():
            with open(path) as f:
                d = json.load(f)
            if d.get("date") == today:
                sessions[label] = d
    return sessions

def build_scorecard(sessions):
    tracker = {}
    for label, data in sessions.items():
        for s in data.get("bullish",[]) + data.get("bearish",[]):
            sym = s["symbol"]
            if sym not in tracker:
                tracker[sym] = {"sessions":{},"probs":[],
                                "entry":s["entry"],"target":s["target"],"sl":s["sl"]}
            tracker[sym]["sessions"][label] = s["direction"]
            tracker[sym]["probs"].append(s["prob"])

    total = len(sessions)
    cb, cs, partial, conflict = [], [], [], []
    for sym, info in tracker.items():
        dirs  = list(info["sessions"].values())
        bulls = dirs.count("BULLISH")
        bears = dirs.count("BEARISH")
        count = len(dirs)
        avg_p = round(sum(info["probs"])/len(info["probs"]))
        dots  = "".join(
            "🟢" if info["sessions"].get(l)=="BULLISH"
            else "🔴" if info["sessions"].get(l)=="BEARISH" else "⚪"
            for l in TRACKING_SESSIONS
        )
        item  = {"symbol":sym,"count":count,"total":total,"prob":avg_p,
                 "dots":dots,"entry":info["entry"],"target":info["target"],"sl":info["sl"]}
        if bulls > 0 and bears > 0: conflict.append(item)
        elif count == total:
            cb.append({**item,"direction":"BULLISH"}) if bulls==total \
            else cs.append({**item,"direction":"BEARISH"})
        elif count >= 2:
            partial.append({**item,"direction":"BULLISH" if bulls>=bears else "BEARISH"})

    return (sorted(cb,key=lambda x:x["prob"],reverse=True),
            sorted(cs,key=lambda x:x["prob"],reverse=True),
            sorted(partial,key=lambda x:x["count"],reverse=True)[:5],
            conflict[:4])

# ─────────────────────────────────────────
# FORMAT MESSAGE
# ─────────────────────────────────────────
def format_message(session, nse_snapshot, ai_analysis, bullish, bearish):
    sess_config = SESSIONS[session]
    now         = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    indices_str = format_indices_summary(nse_snapshot.get("indices", {}))
    upcoming    = nse_snapshot.get("upcoming", [])

    lines = [
        f"📊 *VIRALVIBE STOCK BOT*",
        f"*{sess_config['title']}*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Show indices for key sessions
    if indices_str and session not in ["MORNING_BRIEFING"]:
        lines += ["\n📈 *LIVE MARKET*", indices_str]

    # Holiday warning
    if upcoming and upcoming[0]["days_away"] <= 2:
        h = upcoming[0]
        lines.append(f"\n⚠️ *Holiday Alert:* {h['description']} — {h['display']} ({h['days_away']} day away)")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━")

    # AI Analysis
    if ai_analysis:
        lines += [f"\n🤖 *AI ANALYSIS*\n", ai_analysis]
    else:
        # Fallback
        lines.append("\n📊 *TECHNICAL SIGNALS*")
        if bullish:
            lines.append("🟢 *BULLISH:*")
            for s in bullish[:3]:
                t = "🔥" if s.get("vol_spike") else ""
                m = "⚡" if s.get("cross") else ""
                lines.append(f"• *{s['symbol']}* {t}{m} `{s['prob']}%`  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
        if bearish:
            lines.append("🔴 *BEARISH:*")
            for s in bearish[:3]:
                t = "🔥" if s.get("vol_spike") else ""
                m = "⚡" if s.get("cross") else ""
                lines.append(f"• *{s['symbol']}* {t}{m} `{s['prob']}%`  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
        if not bullish and not bearish:
            lines.append("No strong signals — market uncertain")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ _{sess_config['tip']}_",
        "⚠️ _Education only. Not SEBI advice. Use stop loss._",
        "🤖 _ViralVibe Stock Bot_",
    ]
    return "\n".join(lines)

def format_eod_scorecard(cb, cs, partial, conflict, ai_analysis, nse_snapshot):
    now = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    indices_str = format_indices_summary(nse_snapshot.get("indices", {}))

    lines = [
        "📊 *VIRALVIBE — END OF DAY SCORECARD*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        "\n📈 *MARKET CLOSE*",
        indices_str,
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if ai_analysis:
        lines += ["\n🤖 *AI EOD ANALYSIS*\n", ai_analysis, "\n━━━━━━━━━━━━━━━━━━━━━━━━━"]

    lines.append("\n🏆 *ALL-DAY CONSISTENCY SCORECARD*")
    lines.append(f"_Tracked {len(TRACKING_SESSIONS)} sessions: {' | '.join([s.replace('_',' ') for s in TRACKING_SESSIONS])}_")

    if cb:
        lines.append("\n✅ *CONFIRMED BUY — All sessions agreed*")
        for s in cb:
            lines.append(f"• *{s['symbol']}* {s['dots']}  ({s['count']}/{s['total']})  `{s['prob']}%`\n  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
    if cs:
        lines.append("\n✅ *CONFIRMED SELL — All sessions agreed*")
        for s in cs:
            lines.append(f"• *{s['symbol']}* {s['dots']}  ({s['count']}/{s['total']})  `{s['prob']}%`\n  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
    if not cb and not cs:
        lines.append("\nNo fully confirmed calls today")
    if partial:
        lines.append("\n⚠️ *PARTIAL SIGNALS*")
        for s in partial:
            icon = "🟢" if s.get("direction")=="BULLISH" else "🔴"
            lines.append(f"  {icon} *{s['symbol']}* {s['dots']}  ({s['count']}/{s['total']})  `{s['prob']}%`")
    if conflict:
        lines.append("\n❌ *SKIP — CONFLICTING*")
        for s in conflict:
            lines.append(f"  ⚠️ *{s['symbol']}* {s['dots']}")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🌙 _See you tomorrow! Good trading!_",
        "⚠️ _Education only. Not SEBI advice._",
        "🤖 _ViralVibe Stock Bot_"
    ]
    return "\n".join(lines)

def format_holiday_message(reason, upcoming):
    now   = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    lines = [
        "📅 *VIRALVIBE STOCK BOT*",
        f"🗓 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n🏖 *Market Holiday Today!*",
        f"*{reason}*",
        "\nNSE & BSE closed. No trading today.",
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if upcoming:
        lines.append("\n📅 *Upcoming Holidays:*")
        for h in upcoming[:3]:
            lines.append(f"  • {h['display']} — {h['description']} ({h['days_away']} days away)")
    lines += [
        "\n💡 *Use today wisely:*",
        "  📊 Review your portfolio",
        "  📈 Study tomorrow's watchlist",
        "  📚 Learn a new trading concept",
        "  🧘 Rest and plan your strategy",
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🤖 _ViralVibe Stock Bot — Back on next trading day!_"
    ]
    return "\n".join(lines)

# ─────────────────────────────────────────
# SEND TELEGRAM
# ─────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ No credentials\n")
        print(message[:500])
        return
    for part in [message[i:i+4000] for i in range(0, len(message), 4000)]:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id":TELEGRAM_CHAT_ID,"text":part,"parse_mode":"Markdown"},
                timeout=15
            )
            print("  ✅ Sent!" if r.status_code==200 else f"  ❌ {r.status_code}: {r.text[:100]}")
        except Exception as e:
            print(f"  ❌ {e}")

def save_session(label, bullish, bearish):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    with open(DATA_DIR / f"session_{label}.json", "w") as f:
        json.dump({"session":label,"date":today,
                   "time":datetime.now(IST).strftime("%H:%M"),
                   "bullish":bullish,"bearish":bearish}, f, indent=2)
    print(f"  ✅ Saved session_{label}.json")

def clear_old_data():
    today = datetime.now(IST).strftime("%Y-%m-%d")
    for path in DATA_DIR.glob("session_*.json"):
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get("date") != today:
                path.unlink()
        except Exception:
            path.unlink()

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run():
    print(f"\n{'='*55}")
    print(f"SESSION : {SESSION_LABEL}")
    print(f"TIME    : {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    print("="*55)

    clear_old_data()

    # ── 1. NSE holiday check ──
    print("\n[1] Checking NSE market status...")
    nse_snapshot = get_nse_snapshot()

    if nse_snapshot["is_holiday"]:
        reason   = nse_snapshot["holiday_reason"]
        upcoming = nse_snapshot["upcoming"]
        print(f"  🏖 Holiday: {reason} — sending notice")
        # Only send once per day (morning session)
        if SESSION_LABEL == "MORNING_BRIEFING":
            send_telegram(format_holiday_message(reason, upcoming))
        else:
            print("  Skipping duplicate holiday message")
        return

    print("  ✅ Market open today")

    # ── 2. Fetch news ──
    print("\n[2] Fetching news headlines...")
    headlines = fetch_headlines(SESSION_LABEL)

    # ── 3. Screen stocks (only for relevant sessions) ──
    sess_config = SESSIONS.get(SESSION_LABEL, SESSIONS["MORNING_BRIEFING"])
    bullish, bearish = [], []
    if sess_config["do_screen"]:
        print("\n[3] Screening stocks...")
        bullish, bearish = screen_stocks()
    else:
        print("\n[3] Stock screening skipped for this session")

    # ── 4. Claude AI analysis ──
    print("\n[4] Getting Claude AI analysis...")
    ai_analysis = get_claude_analysis(
        SESSION_LABEL, headlines, nse_snapshot, bullish, bearish
    )

    # ── 5. Format and send ──
    print("\n[5] Sending to Telegram...")

    if SESSION_LABEL == "EOD_SCORECARD":
        sessions = load_all_sessions()
        cb, cs, partial, conflict = build_scorecard(sessions)
        msg = format_eod_scorecard(cb, cs, partial, conflict, ai_analysis, nse_snapshot)

    else:
        # Save data for scorecard tracking sessions
        if SESSION_LABEL in TRACKING_SESSIONS:
            save_session(SESSION_LABEL, bullish, bearish)

        msg = format_message(SESSION_LABEL, nse_snapshot, ai_analysis, bullish, bearish)

    send_telegram(msg)
    print("\n✅ All done!")

if __name__ == "__main__":
    run()

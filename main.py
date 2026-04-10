import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import json
import time
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

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

TRACKING_SESSIONS = ["BEST_ENTRY", "MIDDAY_REVIEW", "POWER_HOUR_PREP", "CLOSING_ANALYSIS"]

# ─────────────────────────────────────────
# SESSION DEFINITIONS
# ─────────────────────────────────────────
SESSIONS = {
    "MORNING_BRIEFING": {
        "title": "☀️ 8:00 AM — MORNING BRIEFING",
        "tip":   "Market opens in 1 hour. Prepare your watchlist now.",
        "focus": """Focus on:
1. Overnight global market movements (US close, Asian open)
2. FII/DII activity from yesterday
3. Key events today (RBI, earnings, macro data)
4. Suggested watchlist of 3-4 stocks to track today
5. Overall market mood for the day
Do NOT give specific entry/exit levels yet — market not open.""",
        "do_screen": False,
    },
    "PRE_OPEN": {
        "title": "🕘 9:00 AM — PRE-OPEN ANALYSIS",
        "tip":   "Pre-open session running. Watch order book for direction.",
        "focus": """Focus on:
1. Pre-open signals — gap up or gap down expected?
2. Key stocks showing large buy/sell orders
3. Initial bias for the day
4. Stocks to watch at open
Keep it brief — only 15 minutes before market opens.""",
        "do_screen": False,
    },
    "MARKET_OPEN": {
        "title": "🔔 9:15 AM — MARKET OPEN",
        "tip":   "Highly volatile! Beginners avoid first 15 minutes.",
        "focus": """Focus on:
1. Opening move — gap up/gap down confirmed
2. Which sectors leading the open
3. High momentum breakout stocks RIGHT NOW
4. Quick scalp opportunities with tight SL
Be very precise — this is fast money window.""",
        "do_screen": True,
    },
    "BEST_ENTRY": {
        "title": "✅ 9:30 AM — BEST ENTRY WINDOW",
        "tip":   "Volatility settling. Best risk-reward window for beginners.",
        "focus": """Focus on:
1. Confirmed trend direction after opening volatility
2. Best 3 stocks for intraday with clear entry/SL/target
3. Nifty support/resistance for the day
4. Stocks showing volume + price confirmation
5. Ideal position sizing suggestion
This is the PRIMARY trading window — be most detailed here.""",
        "do_screen": True,
    },
    "MIDDAY_REVIEW": {
        "title": "☀️ 12:00 PM — MIDDAY REVIEW",
        "tip":   "Low volume period. Review open positions. Avoid new entries.",
        "focus": """Focus on:
1. How morning calls performed — hit target/SL?
2. Current Nifty position vs morning prediction
3. Any news since morning that changed outlook
4. Stocks consolidating for afternoon breakout
5. Position management advice for open trades""",
        "do_screen": True,
    },
    "POWER_HOUR_PREP": {
        "title": "⚡ 2:00 PM — POWER HOUR PREP",
        "tip":   "Last 90 minutes. High liquidity returning. Best momentum trades.",
        "focus": """Focus on:
1. Setup for last 90 minutes of trading
2. Stocks showing afternoon momentum building
3. Whether to hold morning positions or book profit
4. Best 2-3 momentum trades for 2-3:15 PM window
Remember: square off by 3:20 PM for intraday!""",
        "do_screen": True,
    },
    "CLOSING_ANALYSIS": {
        "title": "🔔 3:00 PM — CLOSING ANALYSIS",
        "tip":   "⚠️ 20 minutes left! Close ALL intraday positions by 3:20 PM!",
        "focus": """Focus on:
1. URGENT: Remind to close intraday positions before 3:20 PM
2. Final 30 minutes market direction
3. Any last-minute delivery buys worth holding overnight?
4. Today's key market lesson / takeaway
5. Preview of tomorrow — what to watch""",
        "do_screen": False,
    },
    "EOD_SCORECARD": {
        "title": "📊 3:30 PM — END OF DAY SCORECARD",
        "tip":   "Market closed. Review the full day performance.",
        "focus": """Focus on:
1. Full day summary — Nifty/Sensex/BankNifty final close
2. How the day's bias prediction was right/wrong
3. Which trade setups worked and which failed
4. Key stocks performance today
5. Tomorrow's outlook — what to prepare for""",
        "do_screen": False,
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
# NSE DATA — WITH FULL FALLBACK
# GitHub Actions IPs are often blocked by NSE
# So we handle all failures gracefully
# ─────────────────────────────────────────
NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.nseindia.com/",
}

def safe_nse_get(url, timeout=10):
    """Safe NSE GET with session init. Returns None on any failure."""
    try:
        s = requests.Session()
        s.headers.update(NSE_HEADERS)
        s.get("https://www.nseindia.com", timeout=8)
        time.sleep(1)
        r = s.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None

def fetch_nse_holidays():
    """Fetch NSE holidays. Falls back to hardcoded 2026 list."""
    data = safe_nse_get("https://www.nseindia.com/api/holiday-master?type=trading")
    if data:
        try:
            holidays = []
            for h in data.get("CM", []):
                dt = datetime.strptime(h.get("tradingDate",""), "%d-%b-%Y")
                holidays.append({
                    "date":        dt.strftime("%Y-%m-%d"),
                    "description": h.get("description","Holiday"),
                    "display":     h.get("tradingDate",""),
                })
            if holidays:
                print(f"  ✅ NSE holidays: {len(holidays)} loaded")
                return holidays
        except Exception:
            pass

    print("  ⚠️  Using fallback holiday list")
    return [
        {"date":"2026-04-14","description":"Dr. Ambedkar Jayanti","display":"14-Apr-2026"},
        {"date":"2026-05-01","description":"Maharashtra Day","display":"01-May-2026"},
        {"date":"2026-08-15","description":"Independence Day","display":"15-Aug-2026"},
        {"date":"2026-10-02","description":"Gandhi Jayanti","display":"02-Oct-2026"},
        {"date":"2026-10-22","description":"Diwali Laxmi Pujan","display":"22-Oct-2026"},
        {"date":"2026-11-05","description":"Guru Nanak Jayanti","display":"05-Nov-2026"},
        {"date":"2026-12-25","description":"Christmas","display":"25-Dec-2026"},
    ]

def is_market_holiday(holidays):
    today   = datetime.now(IST).strftime("%Y-%m-%d")
    weekday = datetime.now(IST).weekday()
    if weekday == 5: return True, "Saturday — Market Closed"
    if weekday == 6: return True, "Sunday — Market Closed"
    for h in holidays:
        if h["date"] == today:
            return True, h["description"]
    return False, None

def fetch_nse_indices():
    """Fetch NSE indices. Returns empty dict on failure — not critical."""
    data = safe_nse_get("https://www.nseindia.com/api/allIndices")
    if not data:
        return {}
    result = {}
    targets = ["NIFTY 50","NIFTY BANK","NIFTY IT","NIFTY METAL","NIFTY AUTO","INDIA VIX"]
    for item in data.get("data",[]):
        if item.get("index") in targets:
            result[item["index"]] = {
                "last":    item.get("last",0),
                "change":  item.get("change",0),
                "pChange": item.get("percentChange",0),
            }
    return result

def fetch_fii_dii():
    """Fetch FII/DII data. Returns empty on failure."""
    data = safe_nse_get("https://www.nseindia.com/api/fiidiiTradeReact")
    if not data:
        return []
    result = []
    for row in data[:3]:
        result.append({
            "date":    row.get("date",""),
            "fii_net": row.get("fiiNet",0),
            "dii_net": row.get("diiNet",0),
        })
    return result

def fetch_market_data_yahoo():
    """
    Fallback market data from Yahoo Finance.
    Used when NSE API is blocked.
    """
    tickers = {
        "Nifty50":   "^NSEI",
        "Sensex":    "^BSESN",
        "BankNifty": "^NSEBANK",
        "VIX":       "^INDIAVIX",
        "Crude":     "CL=F",
        "Gold":      "GC=F",
        "USDINR":    "INR=X",
        "SP500":     "^GSPC",
        "Nasdaq":    "^IXIC",
        "Nikkei":    "^N225",
    }
    result = {}
    for name, sym in tickers.items():
        try:
            t     = yf.Ticker(sym)
            info  = t.fast_info
            price = round(float(info.last_price), 2)
            prev  = round(float(info.previous_close), 2)
            chg   = round(((price - prev) / prev) * 100, 2) if prev else 0
            result[name] = {"price": price, "change_pct": chg}
        except Exception:
            result[name] = {"price": 0, "change_pct": 0}
    return result

def get_market_snapshot():
    """
    Get complete market snapshot.
    Tries NSE first, falls back to Yahoo Finance.
    """
    # Holidays
    holidays       = fetch_nse_holidays()
    is_hol, reason = is_market_holiday(holidays)

    # Upcoming holidays
    today    = datetime.now(IST)
    upcoming = []
    for h in holidays:
        try:
            hdate = datetime.strptime(h["date"],"%Y-%m-%d").replace(tzinfo=IST)
            delta = (hdate - today).days
            if 0 < delta <= 7:
                upcoming.append({**h, "days_away": delta})
        except Exception:
            continue

    if is_hol:
        return {
            "is_holiday": True,
            "holiday_reason": reason,
            "upcoming": upcoming,
            "indices": {},
            "fii_dii": [],
            "yahoo": {},
        }

    # Try NSE indices
    print("  Trying NSE indices...")
    indices = fetch_nse_indices()

    # Try FII/DII
    print("  Trying FII/DII...")
    fii_dii = fetch_fii_dii()

    # Always get Yahoo data as backup/supplement
    print("  Fetching Yahoo Finance market data...")
    yahoo = fetch_market_data_yahoo()

    return {
        "is_holiday": False,
        "holiday_reason": None,
        "upcoming": upcoming,
        "indices": indices,        # from NSE (may be empty)
        "fii_dii": fii_dii,        # from NSE (may be empty)
        "yahoo": yahoo,            # from Yahoo (always available)
    }

def format_market_summary(snapshot):
    """Format market data for display and Claude prompt."""
    lines   = []
    yahoo   = snapshot.get("yahoo", {})
    indices = snapshot.get("indices", {})
    fii_dii = snapshot.get("fii_dii", [])

    # Use NSE indices if available, else Yahoo
    def arrow(chg):
        return "🟢" if chg > 0 else "🔴" if chg < 0 else "⚪"

    # Index data
    if indices.get("NIFTY 50"):
        n = indices["NIFTY 50"]
        lines.append(f"📊 Nifty50: {n['last']} {arrow(n['pChange'])} {n['pChange']:+.2f}%")
    elif yahoo.get("Nifty50",{}).get("price"):
        y = yahoo["Nifty50"]
        lines.append(f"📊 Nifty50: {y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")

    if indices.get("NIFTY BANK"):
        n = indices["NIFTY BANK"]
        lines.append(f"🏦 BankNifty: {n['last']} {arrow(n['pChange'])} {n['pChange']:+.2f}%")
    elif yahoo.get("BankNifty",{}).get("price"):
        y = yahoo["BankNifty"]
        lines.append(f"🏦 BankNifty: {y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")

    if indices.get("INDIA VIX"):
        v = indices["INDIA VIX"]
        lines.append(f"⚡ VIX: {v['last']} {arrow(v['pChange'])} {v['pChange']:+.2f}%")
    elif yahoo.get("VIX",{}).get("price"):
        y = yahoo["VIX"]
        lines.append(f"⚡ VIX: {y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")

    # Global
    if yahoo.get("Crude",{}).get("price"):
        y = yahoo["Crude"]
        lines.append(f"🛢 Crude: ${y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")
    if yahoo.get("USDINR",{}).get("price"):
        y = yahoo["USDINR"]
        lines.append(f"💵 USD/INR: {y['price']}")
    if yahoo.get("SP500",{}).get("price"):
        y = yahoo["SP500"]
        lines.append(f"🌏 S&P500: {y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")
    if yahoo.get("Nikkei",{}).get("price"):
        y = yahoo["Nikkei"]
        lines.append(f"🗾 Nikkei: {y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")

    # FII/DII
    if fii_dii:
        latest  = fii_dii[0]
        fii_net = float(latest.get("fii_net",0))
        dii_net = float(latest.get("dii_net",0))
        lines.append(f"🏦 FII: {'BOUGHT' if fii_net>0 else 'SOLD'} ₹{abs(fii_net):.0f}Cr ({latest.get('date','')})")
        lines.append(f"🏦 DII: {'BOUGHT' if dii_net>0 else 'SOLD'} ₹{abs(dii_net):.0f}Cr")

    return "\n".join(lines) if lines else "Market data temporarily unavailable"

# ─────────────────────────────────────────
# TECHNICAL INDICATORS
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
    avg = vol.rolling(p).mean()
    return float(vol.iloc[-1]) > float(avg.iloc[-1]) * 1.5

def calc_prob(rv, hv, price, e50, e200, spike, direction):
    sc = 0
    if direction == "BULLISH":
        if rv < 30:    sc += 1.8
        elif rv < 40:  sc += 1.0
        elif rv < 50:  sc += 0.5
        if hv > 0:     sc += 1.2
        if price > e50: sc += 0.8
        if price > e200: sc += 1.0
        if spike:      sc += 0.5
    else:
        if rv > 70:    sc += 1.8
        elif rv > 60:  sc += 1.0
        elif rv > 50:  sc += 0.5
        if hv < 0:     sc += 1.2
        if price < e50: sc += 0.8
        if price < e200: sc += 1.0
        if spike:      sc += 0.5
    return min(round((sc / 5.5) * 100), 97)

# ─────────────────────────────────────────
# STOCK SCREENER — BATCH + INDIVIDUAL FALLBACK
# ─────────────────────────────────────────
def screen_stocks():
    print(f"  Screening {len(ALL_STOCKS)} stocks...")

    # Try batch download first
    stock_data = {}
    try:
        print("  Downloading all stocks at once...")
        raw = yf.download(
            ALL_STOCKS,
            period="6mo",
            interval="1d",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            timeout=120,
        )
        # Extract per-stock DataFrames from batch result
        for sym in ALL_STOCKS:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    df = raw[sym].dropna()
                else:
                    df = raw.dropna()
                if len(df) >= 50:
                    stock_data[sym] = df
            except Exception:
                pass
        print(f"  ✅ Batch: got data for {len(stock_data)} stocks")
    except Exception as e:
        print(f"  Batch failed ({e}), using individual downloads...")

    # Individual fallback for stocks not in batch
    missing = [s for s in ALL_STOCKS if s not in stock_data]
    if missing:
        print(f"  Individual download for {len(missing)} stocks...")
        for i, sym in enumerate(missing):
            for attempt in range(2):
                try:
                    df = yf.download(sym, period="6mo", interval="1d",
                                     progress=False, auto_adjust=True, timeout=15)
                    if df is not None and len(df) >= 50:
                        stock_data[sym] = df
                    break
                except Exception:
                    if attempt == 0:
                        time.sleep(random.uniform(1, 3))
            if i % 15 == 0 and i > 0:
                time.sleep(random.uniform(1, 2))

    print(f"  Total stocks with data: {len(stock_data)}")

    # Analyze each stock
    results = []
    for sym, df in stock_data.items():
        try:
            close  = df["Close"].squeeze()
            volume = df["Volume"].squeeze()

            if len(close) < 50:
                continue

            price  = float(close.iloc[-1])
            if price <= 0:
                continue

            rv    = float(rsi(close).iloc[-1])
            h     = macd_hist(close)
            hv    = float(h.iloc[-1])
            hp    = float(h.iloc[-2])
            e50   = float(ema(close, 50).iloc[-1])
            e200  = float(ema(close, 200).iloc[-1])
            spike = vol_spike(volume)
            cross = (hv > 0 and hp <= 0) or (hv < 0 and hp >= 0)
            atr   = float((df["High"] - df["Low"]).squeeze().rolling(14).mean().iloc[-1])

            bp = calc_prob(rv, hv, price, e50, e200, spike, "BULLISH")
            sp = calc_prob(rv, hv, price, e50, e200, spike, "BEARISH")

            name = sym.replace(".NS","")

            if bp >= 50 and bp > sp:
                results.append({"symbol":name,"direction":"BULLISH","prob":bp,
                                 "entry":round(price,2),"target":round(price+atr*2,2),
                                 "sl":round(price-atr,2),"rsi":round(rv,1),
                                 "vol_spike":spike,"cross":cross})
            elif sp >= 50 and sp > bp:
                results.append({"symbol":name,"direction":"BEARISH","prob":sp,
                                 "entry":round(price,2),"target":round(price-atr*2,2),
                                 "sl":round(price+atr,2),"rsi":round(rv,1),
                                 "vol_spike":spike,"cross":cross})
        except Exception as e:
            print(f"  Skipped {sym}: {e}")
            continue

    bullish = sorted([r for r in results if r["direction"]=="BULLISH"],
                     key=lambda x: x["prob"], reverse=True)[:5]
    bearish = sorted([r for r in results if r["direction"]=="BEARISH"],
                     key=lambda x: x["prob"], reverse=True)[:5]

    print(f"  ✅ Found: {len(bullish)} bullish, {len(bearish)} bearish")
    return bullish, bearish

# ─────────────────────────────────────────
# NEWS FETCHER
# ─────────────────────────────────────────
def fetch_headlines(session):
    feeds_map = {
        "MORNING_BRIEFING": [
            "https://news.google.com/rss/search?q=US+market+overnight+Asia+India+stocks&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=NSE+Nifty+India+stock+market+today&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=RBI+crude+oil+rupee+India+economy&hl=en-IN&gl=IN&ceid=IN:en",
        ],
        "EOD_SCORECARD": [
            "https://news.google.com/rss/search?q=Sensex+Nifty+close+today+India&hl=en-IN&gl=IN&ceid=IN:en",
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
        except Exception:
            pass
    seen, unique = set(), []
    for h in all_h:
        if h.lower() not in seen:
            seen.add(h.lower())
            unique.append(h)
    print(f"  Fetched {len(unique)} headlines")
    return unique[:18]

# ─────────────────────────────────────────
# CLAUDE AI ANALYSIS
# ─────────────────────────────────────────
def get_claude_analysis(session, headlines, market_summary, bullish, bearish):
    if not ANTHROPIC_API_KEY:
        return None

    sess_config = SESSIONS.get(session, SESSIONS["MORNING_BRIEFING"])
    today       = datetime.now(IST).strftime("%d %b %Y %A")
    time_now    = datetime.now(IST).strftime("%I:%M %p")

    bull_str = "\n".join([
        f"  {s['symbol']}: RSI {s['rsi']} Prob {s['prob']}% Entry ₹{s['entry']} T ₹{s['target']} SL ₹{s['sl']}"
        for s in bullish[:3]
    ]) or "  None found"

    bear_str = "\n".join([
        f"  {s['symbol']}: RSI {s['rsi']} Prob {s['prob']}% Entry ₹{s['entry']} T ₹{s['target']} SL ₹{s['sl']}"
        for s in bearish[:3]
    ]) or "  None found"

    news_str = "\n".join([f"- {h}" for h in headlines[:15]])

    # Load previous context
    prev_ctx  = ""
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    for label in TRACKING_SESSIONS:
        path = DATA_DIR / f"session_{label}.json"
        if path.exists():
            try:
                with open(path) as f:
                    d = json.load(f)
                if d.get("date") == today_str:
                    prev_ctx += f"\n{label}: {len(d.get('bullish',[]))} bullish, {len(d.get('bearish',[]))} bearish calls"
            except Exception:
                pass

    prompt = f"""You are a senior professional Indian stock market analyst. 
Today: {today} | Time: {time_now} IST | Session: {session}

MARKET DATA:
{market_summary}

LATEST NEWS:
{news_str}

TECHNICAL SCREENER:
Bullish signals:
{bull_str}
Bearish signals:
{bear_str}

PREVIOUS SESSIONS TODAY:{prev_ctx or ' First session of day'}

SESSION FOCUS — {session}:
{sess_config['focus']}

Write professional analysis following the session focus.
Plain text only. No markdown symbols.
Keep total under 500 words. Be specific with price levels.
End with: CONFIDENCE: [HIGH/MEDIUM/LOW] | BIAS: [BULLISH/BEARISH/SIDEWAYS]"""

    try:
        print("  Calling Claude AI...")
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 1100,
                "messages":   [{"role":"user","content":prompt}],
            },
            timeout=35
        )
        if res.status_code == 200:
            print("  ✅ Claude done")
            return res.json()["content"][0]["text"]
        print(f"  ❌ Claude error: {res.status_code} — {res.text[:100]}")
        return None
    except Exception as e:
        print(f"  ❌ Claude failed: {e}")
        return None

# ─────────────────────────────────────────
# SESSION DATA — SAVE / LOAD / SCORECARD
# ─────────────────────────────────────────
def save_session(label, bullish, bearish):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    with open(DATA_DIR / f"session_{label}.json","w") as f:
        json.dump({"session":label,"date":today,
                   "time":datetime.now(IST).strftime("%H:%M"),
                   "bullish":bullish,"bearish":bearish}, f, indent=2)
    print(f"  ✅ Saved session_{label}.json")

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
        item = {"symbol":sym,"count":count,"total":total,
                "prob":avg_p,"dots":dots,
                "entry":info["entry"],"target":info["target"],"sl":info["sl"]}

        if bulls>0 and bears>0:          conflict.append(item)
        elif count==total:
            cb.append({**item,"direction":"BULLISH"}) if bulls==total \
            else cs.append({**item,"direction":"BEARISH"})
        elif count>=2:
            partial.append({**item,"direction":"BULLISH" if bulls>=bears else "BEARISH"})

    return (sorted(cb,  key=lambda x:x["prob"],reverse=True),
            sorted(cs,  key=lambda x:x["prob"],reverse=True),
            sorted(partial,key=lambda x:x["count"],reverse=True)[:5],
            conflict[:4])

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
# FORMAT MESSAGES
# ─────────────────────────────────────────
def format_regular_message(session, market_summary, ai_analysis, bullish, bearish, snapshot):
    sess   = SESSIONS.get(session, SESSIONS["MORNING_BRIEFING"])
    now    = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    upcoming = snapshot.get("upcoming",[])

    lines = [
        "📊 *VIRALVIBE STOCK BOT*",
        f"*{sess['title']}*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n{market_summary}",
    ]

    if upcoming and upcoming[0]["days_away"] <= 2:
        h = upcoming[0]
        lines.append(f"\n⚠️ *Holiday Alert:* {h['description']} — {h['display']} ({h['days_away']} day away)")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━")

    if ai_analysis:
        lines += ["\n🤖 *AI ANALYSIS*\n", ai_analysis]
    else:
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
        f"⏰ _{sess['tip']}_",
        "⚠️ _Education only. Not SEBI advice. Use stop loss._",
        "🤖 _ViralVibe Stock Bot_",
    ]
    return "\n".join(lines)

def format_eod_scorecard(cb, cs, partial, conflict, ai_analysis, market_summary):
    now = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    lines = [
        "📊 *VIRALVIBE — END OF DAY SCORECARD*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n{market_summary}",
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if ai_analysis:
        lines += ["\n🤖 *AI EOD ANALYSIS*\n", ai_analysis, "\n━━━━━━━━━━━━━━━━━━━━━━━━━"]

    lines.append("\n🏆 *ALL-DAY CONSISTENCY SCORECARD*")
    lines.append(f"_Sessions tracked: {' | '.join(TRACKING_SESSIONS)}_")

    if cb:
        lines.append("\n✅ *CONFIRMED BUY — All sessions agreed*")
        for s in cb:
            lines.append(f"• *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`\n  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
    if cs:
        lines.append("\n✅ *CONFIRMED SELL — All sessions agreed*")
        for s in cs:
            lines.append(f"• *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`\n  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
    if not cb and not cs:
        lines.append("\nNo fully confirmed calls today")
    if partial:
        lines.append("\n⚠️ *PARTIAL SIGNALS*")
        for s in partial:
            icon = "🟢" if s.get("direction")=="BULLISH" else "🔴"
            lines.append(f"  {icon} *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`")
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
    now = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    lines = [
        "📅 *VIRALVIBE STOCK BOT*",
        f"🗓 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n🏖 *Market Holiday Today!*",
        f"*{reason}*",
        "\nNSE & BSE closed. No trading today.",
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
    for part in [message[i:i+4000] for i in range(0,len(message),4000)]:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id":TELEGRAM_CHAT_ID,"text":part,"parse_mode":"Markdown"},
                timeout=15
            )
            print("  ✅ Sent!" if r.status_code==200 else f"  ❌ {r.status_code}: {r.text[:80]}")
        except Exception as e:
            print(f"  ❌ {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run():
    print(f"\n{'='*55}")
    print(f"SESSION : {SESSION_LABEL}")
    print(f"TIME    : {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    print("="*55)

    clear_old_data()

    # 1. Market snapshot (NSE + Yahoo fallback)
    print("\n[1] Getting market snapshot...")
    snapshot = get_market_snapshot()

    if snapshot["is_holiday"]:
        reason   = snapshot["holiday_reason"]
        upcoming = snapshot["upcoming"]
        print(f"  🏖 Holiday: {reason}")
        if SESSION_LABEL in ["MORNING_BRIEFING", "BEST_ENTRY"]:
            send_telegram(format_holiday_message(reason, upcoming))
        else:
            print("  Skipping duplicate holiday message")
        return

    print("  ✅ Market open today")
    market_summary = format_market_summary(snapshot)
    print(f"  Market data:\n{market_summary[:200]}...")

    # 2. News
    print("\n[2] Fetching headlines...")
    headlines = fetch_headlines(SESSION_LABEL)

    # 3. Screen stocks
    sess_config = SESSIONS.get(SESSION_LABEL, SESSIONS["MORNING_BRIEFING"])
    bullish, bearish = [], []
    if sess_config["do_screen"]:
        print("\n[3] Screening stocks...")
        bullish, bearish = screen_stocks()
    else:
        print("\n[3] Stock screening skipped for this session")

    # 4. Claude analysis
    print("\n[4] Getting Claude AI analysis...")
    ai_analysis = get_claude_analysis(
        SESSION_LABEL, headlines, market_summary, bullish, bearish
    )

    # 5. Format and send
    print("\n[5] Sending to Telegram...")
    if SESSION_LABEL == "EOD_SCORECARD":
        sessions = load_all_sessions()
        cb, cs, partial, conflict = build_scorecard(sessions)
        msg = format_eod_scorecard(cb, cs, partial, conflict, ai_analysis, market_summary)
    else:
        if SESSION_LABEL in TRACKING_SESSIONS:
            save_session(SESSION_LABEL, bullish, bearish)
        msg = format_regular_message(
            SESSION_LABEL, market_summary, ai_analysis, bullish, bearish, snapshot
        )

    send_telegram(msg)
    print("\n✅ All done!")

if __name__ == "__main__":
    run()

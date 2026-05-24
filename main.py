import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import json
import time
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─────────────────────────────────────────
# CONFIG — GitHub Secrets
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY",  "")

_env_session  = os.getenv("SESSION_LABEL", "")
SESSION_LABEL = _env_session if _env_session else "AUTO"

IST      = timezone(timedelta(hours=5, minutes=30))
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

TRACKING_SESSIONS = ["BEST_ENTRY", "MIDDAY_REVIEW", "POWER_HOUR_PREP", "CLOSING_ANALYSIS"]

# ─────────────────────────────────────────
# AUTO-DETECT SESSION FROM REAL IST TIME
# ─────────────────────────────────────────
def detect_session_from_time():
    total = datetime.now(IST).hour * 60 + datetime.now(IST).minute
    if total < 8*60+45:    return "MORNING_BRIEFING"
    elif total < 9*60+10:  return "PRE_OPEN"
    elif total < 9*60+25:  return "MARKET_OPEN"
    elif total < 11*60:    return "BEST_ENTRY"
    elif total < 13*60+30: return "MIDDAY_REVIEW"
    elif total < 15*60:    return "POWER_HOUR_PREP"
    elif total < 15*60+25: return "CLOSING_ANALYSIS"
    elif total < 18*60:    return "EOD_SCORECARD"
    else:                  return "MORNING_BRIEFING"

# ─────────────────────────────────────────
# SESSION DEFINITIONS
# ─────────────────────────────────────────
SESSIONS = {
    "MORNING_BRIEFING": {
        "title":     "☀️ 8:00 AM — MORNING BRIEFING",
        "tip":       "Market opens in 1 hour. Prepare your watchlist now.",
        "do_screen": False,
        "focus": """Focus on:
1. Overnight global market movements (US close, Asian open)
2. FII/DII activity from yesterday
3. Key events today (RBI, earnings, macro data)
4. Suggested watchlist of 3-4 stocks to track today
5. Overall market mood — bullish/bearish/sideways
Do NOT give specific entry/exit levels yet — market not open.""",
    },
    "PRE_OPEN": {
        "title":     "🕘 9:00 AM — PRE-OPEN ANALYSIS",
        "tip":       "Pre-open session running. Watch order book for direction.",
        "do_screen": False,
        "focus": """Focus on:
1. Gap up or gap down expected today?
2. Key stocks showing large buy/sell orders
3. Initial bias for the day
4. 2-3 stocks to watch at open with levels""",
    },
    "MARKET_OPEN": {
        "title":     "🔔 9:15 AM — MARKET OPEN",
        "tip":       "Highly volatile! Beginners avoid first 15 minutes.",
        "do_screen": True,
        "focus": """Focus on:
1. Opening move confirmed — gap up/gap down
2. Which sectors are leading the open
3. Top 2-3 breakout stocks with entry levels
4. Quick scalp opportunities with tight SL""",
    },
    "BEST_ENTRY": {
        "title":     "✅ 9:30 AM — BEST ENTRY WINDOW",
        "tip":       "Volatility settling. Best risk-reward window for beginners.",
        "do_screen": True,
        "focus": """Focus on:
1. Confirmed trend direction after opening volatility
2. Best 3 stocks for intraday — entry/SL/target
3. Nifty key support and resistance for today
4. Volume confirmation analysis
5. Pattern success rate from last 3 similar setups
6. Risk management: position size for 2% account risk, 1:3 R:R
This is the PRIMARY session — be most detailed here.""",
    },
    "MIDDAY_REVIEW": {
        "title":     "☀️ 12:00 PM — MIDDAY REVIEW",
        "tip":       "Low volume. Review open positions. Avoid new entries.",
        "do_screen": True,
        "focus": """Focus on:
1. How morning calls performed — target hit or SL hit?
2. Current Nifty vs morning prediction — accurate?
3. Any breaking news that changed market direction
4. Stocks consolidating for afternoon breakout
5. Advice for managing open positions""",
    },
    "POWER_HOUR_PREP": {
        "title":     "⚡ 2:00 PM — POWER HOUR PREP",
        "tip":       "Last 90 min. High liquidity. Square off by 3:20 PM!",
        "do_screen": True,
        "focus": """Focus on:
1. Best 2-3 momentum setups for 2 PM to 3:15 PM window
2. Stocks showing afternoon momentum building
3. Whether to hold morning positions or book profit now
4. F&O expiry impact if applicable
IMPORTANT: Square off all intraday positions before 3:20 PM!""",
    },
    "CLOSING_ANALYSIS": {
        "title":     "🔔 3:00 PM — CLOSING ANALYSIS",
        "tip":       "⚠️ 20 minutes left! Close ALL intraday by 3:20 PM!",
        "do_screen": False,
        "focus": """Focus on:
1. URGENT: Close all intraday positions before 3:20 PM
2. Final 30 minutes expected market direction
3. Any delivery stocks worth holding overnight?
4. Today's key lesson for traders
5. What to watch tomorrow""",
    },
    "EOD_SCORECARD": {
        "title":     "📊 3:30 PM — END OF DAY SCORECARD",
        "tip":       "Market closed. Great trading today!",
        "do_screen": False,
        "focus": """Focus on:
1. Final Nifty/Sensex/BankNifty closing numbers
2. Was today's morning bias correct? What worked and what failed?
3. Top gainers and losers today
4. Tomorrow's key levels and what to watch
5. Any overnight positions worth considering""",
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
# NSE + YAHOO MARKET DATA
# ─────────────────────────────────────────
NSE_HEADERS = {
    "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":      "application/json, text/plain, */*",
    "Referer":     "https://www.nseindia.com/",
}

def safe_nse_get(url, timeout=10):
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
    data = safe_nse_get("https://www.nseindia.com/api/holiday-master?type=trading")
    if data:
        try:
            holidays = []
            for h in data.get("CM", []):
                dt = datetime.strptime(h.get("tradingDate", ""), "%d-%b-%Y")
                holidays.append({
                    "date":        dt.strftime("%Y-%m-%d"),
                    "description": h.get("description", "Holiday"),
                    "display":     h.get("tradingDate", ""),
                })
            if holidays:
                return holidays
        except Exception:
            pass
    # Fallback 2026 list
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
    data = safe_nse_get("https://www.nseindia.com/api/allIndices")
    if not data:
        return {}
    result  = {}
    targets = ["NIFTY 50","NIFTY BANK","NIFTY IT","NIFTY METAL","NIFTY AUTO","INDIA VIX"]
    for item in data.get("data", []):
        if item.get("index") in targets:
            result[item["index"]] = {
                "last":    item.get("last", 0),
                "change":  item.get("change", 0),
                "pChange": item.get("percentChange", 0),
            }
    return result

def fetch_fii_dii():
    data = safe_nse_get("https://www.nseindia.com/api/fiidiiTradeReact")
    if data:
        result = []
        for row in data[:3]:
            fii = float(row.get("fiiNet", 0) or 0)
            dii = float(row.get("diiNet", 0) or 0)
            if fii != 0 or dii != 0:
                result.append({
                    "date":    row.get("date", ""),
                    "fii_net": fii,
                    "dii_net": dii,
                })
        if result:
            return result
    try:
        r = requests.get(
            "https://trendlyne.com/macro-data/fii-dii/latest/snapshot-pastmonth/",
            timeout=8, headers={"User-Agent": "Mozilla/5.0"}
        )
        matches = re.findall(r'([+-]?[\d,]+\.?\d*)\s*Cr', r.text)
        if len(matches) >= 2:
            fii = float(matches[0].replace(",", ""))
            dii = float(matches[1].replace(",", ""))
            if fii != 0 or dii != 0:
                return [{"date": "latest", "fii_net": fii, "dii_net": dii}]
    except Exception:
        pass
    return []

def fetch_market_data_yahoo():
    tickers = {
        "Nifty50":   "^NSEI",
        "Sensex":    "^BSESN",
        "BankNifty": "^NSEBANK",
        "NiftyIT":   "^CNXIT",
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
    holidays       = fetch_nse_holidays()
    is_hol, reason = is_market_holiday(holidays)
    today          = datetime.now(IST)
    upcoming       = []
    for h in holidays:
        try:
            hdate = datetime.strptime(h["date"], "%Y-%m-%d").replace(tzinfo=IST)
            delta = (hdate - today).days
            if 0 < delta <= 7:
                upcoming.append({**h, "days_away": delta})
        except Exception:
            continue
    if is_hol:
        return {"is_holiday": True, "holiday_reason": reason, "upcoming": upcoming,
                "indices": {}, "fii_dii": [], "yahoo": {}}
    return {
        "is_holiday":    False,
        "holiday_reason": None,
        "upcoming":      upcoming,
        "indices":       fetch_nse_indices(),
        "fii_dii":       fetch_fii_dii(),
        "yahoo":         fetch_market_data_yahoo(),
    }

def format_market_summary(snapshot):
    lines   = []
    yahoo   = snapshot.get("yahoo", {})
    indices = snapshot.get("indices", {})
    fii_dii = snapshot.get("fii_dii", [])

    def arrow(c): return "🟢" if c > 0 else "🔴" if c < 0 else "⚪"
    def yv(k):    return yahoo.get(k, {})

    for nkey, ykey, icon, label in [
        ("NIFTY 50",   "Nifty50",   "📊", "Nifty50"),
        ("NIFTY BANK", "BankNifty", "🏦", "BankNifty"),
        ("NIFTY IT",   "NiftyIT",   "💻", "NiftyIT"),
        ("INDIA VIX",  "VIX",       "⚡", "VIX"),
    ]:
        if indices.get(nkey):
            n = indices[nkey]
            lines.append(f"{icon} {label}: {n['last']} {arrow(n['pChange'])} {n['pChange']:+.2f}%")
        elif yv(ykey).get("price"):
            y = yv(ykey)
            lines.append(f"{icon} {label}: {y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")

    for k, icon, pre in [
        ("Crude",  "🛢",  "$"),
        ("Gold",   "🥇",  "$"),
        ("SP500",  "🌏",  ""),
        ("Nasdaq", "💻",  ""),
        ("Nikkei", "🗾",  ""),
    ]:
        if yv(k).get("price"):
            y = yv(k)
            lines.append(f"{icon} {k}: {pre}{y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")

    if yv("USDINR").get("price"):
        lines.append(f"💵 USD/INR: ₹{yv('USDINR')['price']}")

    if fii_dii:
        l   = fii_dii[0]
        fn  = float(l.get("fii_net", 0))
        dn  = float(l.get("dii_net", 0))
        lines.append(
            f"🏦 FII: {'🟢 BOUGHT' if fn>0 else '🔴 SOLD'} ₹{abs(fn):.0f}Cr  "
            f"DII: {'🟢 BOUGHT' if dn>0 else '🔴 SOLD'} ₹{abs(dn):.0f}Cr  ({l.get('date','')})"
        )
        if len(fii_dii) >= 2:
            fii_days = sum(1 for d in fii_dii if float(d.get("fii_net", 0)) > 0)
            lines.append(f"   📈 FII trend: buying {fii_days}/{len(fii_dii)} recent days")
    else:
        lines.append("🏦 FII/DII: Updating — check NSE after 7 PM")

    return "\n".join(lines) if lines else "Market data loading..."

# ─────────────────────────────────────────
# TECHNICAL INDICATORS
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

def vol_spike(vol, p=20):
    avg = vol.rolling(p).mean()
    return float(vol.iloc[-1]) > float(avg.iloc[-1]) * 1.5

def calc_prob(rv, hv, price, e50, e200, spike, direction):
    sc = 0
    if direction == "BULLISH":
        if rv < 30:      sc += 1.8
        elif rv < 40:    sc += 1.0
        elif rv < 50:    sc += 0.5
        if hv > 0:       sc += 1.2
        if price > e50:  sc += 0.8
        if price > e200: sc += 1.0
        if spike:        sc += 0.5
    else:
        if rv > 70:      sc += 1.8
        elif rv > 60:    sc += 1.0
        elif rv > 50:    sc += 0.5
        if hv < 0:       sc += 1.2
        if price < e50:  sc += 0.8
        if price < e200: sc += 1.0
        if spike:        sc += 0.5
    return min(round((sc / 5.5) * 100), 97)

# ─────────────────────────────────────────
# STOCK SCREENER — BATCH + FALLBACK
# ─────────────────────────────────────────
def screen_stocks():
    print(f"  Screening {len(ALL_STOCKS)} stocks...")
    stock_data = {}

    # Batch download
    try:
        print("  Batch downloading...")
        raw = yf.download(
            ALL_STOCKS, period="6mo", interval="1d",
            progress=False, auto_adjust=True,
            group_by="ticker", timeout=120
        )
        for sym in ALL_STOCKS:
            try:
                df = raw[sym].dropna() if isinstance(raw.columns, pd.MultiIndex) else raw.dropna()
                if len(df) >= 50:
                    stock_data[sym] = df
            except Exception:
                pass
        print(f"  ✅ Batch: {len(stock_data)} stocks")
    except Exception as e:
        print(f"  Batch failed: {e}")

    # Individual fallback
    missing = [s for s in ALL_STOCKS if s not in stock_data]
    if missing:
        print(f"  Individual: {len(missing)} remaining...")
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

    print(f"  Total: {len(stock_data)} stocks with data")
    results = []

    for sym, df in stock_data.items():
        try:
            close  = df["Close"].squeeze()
            high   = df["High"].squeeze()
            low    = df["Low"].squeeze()
            volume = df["Volume"].squeeze()
            if len(close) < 50: continue
            price = float(close.iloc[-1])
            if price <= 0: continue

            curr_rsi = float(rsi(close).iloc[-1])
            prev_rsi = float(rsi(close).iloc[-5])
            h    = macd_hist(close)
            hv   = float(h.iloc[-1])
            hp   = float(h.iloc[-2])
            e50  = float(ema(close, 50).iloc[-1])
            e200 = float(ema(close, 200).iloc[-1])
            spk  = vol_spike(volume)
            crs  = (hv > 0 and hp <= 0) or (hv < 0 and hp >= 0)
            atr  = float((high - low).rolling(14).mean().iloc[-1])

            # Support / Resistance
            recent     = close.tail(60)
            resistance = round(float(recent.nlargest(5).mean()), 2)
            support    = round(float(recent.nsmallest(5).mean()), 2)

            # RSI divergence
            bullish_div = price < float(close.iloc[-5]) and curr_rsi > prev_rsi
            bearish_div = price > float(close.iloc[-5]) and curr_rsi < prev_rsi

            # Historical pattern success
            rv_series = rsi(close)
            patterns  = []
            for i in range(20, len(close) - 5):
                if abs(float(rv_series.iloc[i]) - curr_rsi) < 5:
                    pp = float(close.iloc[i])
                    fp = float(close.iloc[i + 5])
                    patterns.append("UP" if fp > pp else "DOWN")
            patterns     = patterns[-3:]
            pattern_rate = round((patterns.count("UP") / len(patterns)) * 100) if patterns else 50

            bp = calc_prob(curr_rsi, hv, price, e50, e200, spk, "BULLISH")
            sp = calc_prob(curr_rsi, hv, price, e50, e200, spk, "BEARISH")
            name = sym.replace(".NS", "")

            if bp >= 50 and bp > sp:
                results.append({
                    "symbol": name, "direction": "BULLISH", "prob": bp,
                    "entry":  round(price, 2),
                    "target": round(price + atr * 3, 2),
                    "sl":     round(price - atr, 2),
                    "rsi": round(curr_rsi, 1), "atr": round(atr, 2),
                    "vol_spike": spk, "cross": crs,
                    "support": support, "resistance": resistance,
                    "bullish_div": bullish_div, "bearish_div": bearish_div,
                    "pattern_rate": pattern_rate,
                    "ema50": round(e50, 2), "ema200": round(e200, 2),
                })
            elif sp >= 50 and sp > bp:
                results.append({
                    "symbol": name, "direction": "BEARISH", "prob": sp,
                    "entry":  round(price, 2),
                    "target": round(price - atr * 3, 2),
                    "sl":     round(price + atr, 2),
                    "rsi": round(curr_rsi, 1), "atr": round(atr, 2),
                    "vol_spike": spk, "cross": crs,
                    "support": support, "resistance": resistance,
                    "bullish_div": bullish_div, "bearish_div": bearish_div,
                    "pattern_rate": pattern_rate,
                    "ema50": round(e50, 2), "ema200": round(e200, 2),
                })
        except Exception as e:
            print(f"  Skipped {sym}: {e}")

    bullish = sorted([r for r in results if r["direction"] == "BULLISH"],
                     key=lambda x: x["prob"], reverse=True)[:5]
    bearish = sorted([r for r in results if r["direction"] == "BEARISH"],
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
            "https://news.google.com/rss/search?q=RBI+crude+oil+rupee+India&hl=en-IN&gl=IN&ceid=IN:en",
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
            r    = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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
# AI ANALYSIS — OPENROUTER + MINIMAX M2.5 FREE
# 3-PROMPT FRAMEWORK
# ─────────────────────────────────────────
def format_stock_details_for_prompt(stocks):
    if not stocks:
        return "  None found"
    lines = []
    for s in stocks[:3]:
        tags = []
        if s.get("bullish_div"):  tags.append("BULLISH DIVERGENCE")
        if s.get("bearish_div"):  tags.append("BEARISH DIVERGENCE")
        if s.get("vol_spike"):    tags.append("VOLUME SPIKE")
        if s.get("cross"):        tags.append("MACD CROSSOVER")
        lines.append(
            f"\n  {s['symbol']} | {s['direction']} | Probability: {s['prob']}%"
            f"\n  Price: Rs{s['entry']} | EMA50: Rs{s.get('ema50','?')} | EMA200: Rs{s.get('ema200','?')}"
            f"\n  Support: Rs{s.get('support','?')} | Resistance: Rs{s.get('resistance','?')}"
            f"\n  RSI: {s['rsi']} | ATR: Rs{s.get('atr','?')}"
            f"\n  Historical pattern success (last 3 similar): {s.get('pattern_rate','?')}%"
            f"\n  Entry: Rs{s['entry']} | Target: Rs{s['target']} (1:3 RR) | SL: Rs{s['sl']}"
            + (f"\n  Signals: {' | '.join(tags)}" if tags else "")
        )
    return "\n".join(lines)

def get_ai_analysis(session, headlines, market_summary, bullish, bearish):
    if not OPENROUTER_API_KEY:
        print("  ⚠️ No OPENROUTER_API_KEY found — skipping AI analysis")
        return None

    today    = datetime.now(IST).strftime("%d %b %Y %A")
    time_now = datetime.now(IST).strftime("%I:%M %p")
    sess     = SESSIONS.get(session, SESSIONS["MORNING_BRIEFING"])
    news_str = "\n".join([f"- {h}" for h in headlines[:15]])
    bull_str = format_stock_details_for_prompt(bullish)
    bear_str = format_stock_details_for_prompt(bearish)

    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    prev_ctx  = ""
    for label in TRACKING_SESSIONS:
        path = DATA_DIR / f"session_{label}.json"
        if path.exists():
            try:
                with open(path) as f:
                    d = json.load(f)
                if d.get("date") == today_str:
                    prev_ctx += f"\n{label}: {len(d.get('bullish',[]))} bullish, {len(d.get('bearish',[]))} bearish"
            except Exception:
                pass

    prompt = f"""You are a senior professional Indian stock market analyst.
Today: {today} | Time: {time_now} IST | Session: {session}

MARKET DATA:
{market_summary}

LATEST NEWS:
{news_str}

BULLISH SIGNALS (with technical data):
{bull_str}

BEARISH SIGNALS (with technical data):
{bear_str}

PREVIOUS SESSIONS TODAY:{prev_ctx or ' First session of day'}

SESSION FOCUS:
{sess['focus']}

Provide professional analysis using these 3 frameworks:

PROMPT 1 - CHART ANALYSIS:
For top signals, analyze Support/Resistance, Volume zones, RSI divergence.
Give 3 scenarios per top stock:
BULLISH SCENARIO: Entry Rs[x] | Target Rs[x] | Condition: [what must happen]
BEARISH SCENARIO: Entry Rs[x] | Target Rs[x] | Condition: [what must happen]
NEUTRAL SCENARIO: Range [x]-[x] | Watch for: [breakout trigger]

PROMPT 2 - PATTERN HISTORY:
For each top stock:
Last 3 similar RSI setups in past 6 months - what happened after
Pattern success rate: [X]% bullish outcome
Recommendation based on history

PROMPT 3 - RISK MANAGER:
For each trade (assume Rs1,00,000 account size):
2% account risk = Rs2,000 max loss per trade
Position size = Rs2,000 divided by (Entry minus SL) = [X] shares
Maintain 1:3 Risk Reward ratio
SL: Rs[x] | Target 1: Rs[x] | Target 2: Rs[x]

Format:
MARKET BIAS: [BULLISH/BEARISH/SIDEWAYS] | CONFIDENCE: [HIGH/MEDIUM/LOW]
STRATEGY: [Buy on Dips / Sell on Rise / Avoid]

Then apply all 3 prompts for top 2-3 stocks.

End with:
KEY LEVELS: Nifty Support [x]/[x] | Resistance [x]/[x]
CONFIDENCE: [HIGH/MEDIUM/LOW] | BIAS: [BULLISH/BEARISH/SIDEWAYS]

Keep total under 600 words. Be specific with price levels. Plain text only."""

    try:
        print("  Calling MiniMax M2.5 via OpenRouter...")
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type":  "application/json",
                "HTTP-Referer":  "https://github.com/allinwon9-bot/viralvibe-stock-screener",
                "X-Title":       "ViralVibe Stock Bot",
            },
            json={
                "model":      "minimax/minimax-m2.5:free",
                "max_tokens": 1400,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=40
        )
        if res.status_code == 200:
            print("  ✅ MiniMax M2.5 analysis done!")
            return res.json()["choices"][0]["message"]["content"]
        print(f"  ❌ OpenRouter error: {res.status_code} — {res.text[:150]}")
        return None
    except Exception as e:
        print(f"  ❌ AI analysis failed: {e}")
        return None

# ─────────────────────────────────────────
# SESSION DATA — SAVE / LOAD / SCORECARD
# ─────────────────────────────────────────
def save_session(label, bullish, bearish):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    with open(DATA_DIR / f"session_{label}.json", "w") as f:
        json.dump({
            "session": label, "date": today,
            "time":    datetime.now(IST).strftime("%H:%M"),
            "bullish": bullish, "bearish": bearish,
        }, f, indent=2)
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
        for s in data.get("bullish", []) + data.get("bearish", []):
            sym = s["symbol"]
            if sym not in tracker:
                tracker[sym] = {"sessions": {}, "probs": [],
                                "entry": s["entry"], "target": s["target"], "sl": s["sl"]}
            tracker[sym]["sessions"][label] = s["direction"]
            tracker[sym]["probs"].append(s["prob"])
    total = len(sessions)
    cb, cs, partial, conflict = [], [], [], []
    for sym, info in tracker.items():
        dirs  = list(info["sessions"].values())
        bulls = dirs.count("BULLISH")
        bears = dirs.count("BEARISH")
        count = len(dirs)
        avg_p = round(sum(info["probs"]) / len(info["probs"]))
        dots  = "".join(
            "🟢" if info["sessions"].get(l) == "BULLISH"
            else "🔴" if info["sessions"].get(l) == "BEARISH" else "⚪"
            for l in TRACKING_SESSIONS
        )
        item = {"symbol": sym, "count": count, "total": total, "prob": avg_p,
                "dots": dots, "entry": info["entry"], "target": info["target"], "sl": info["sl"]}
        if bulls > 0 and bears > 0:    conflict.append(item)
        elif count == total:
            cb.append({**item, "direction": "BULLISH"}) if bulls == total \
            else cs.append({**item, "direction": "BEARISH"})
        elif count >= 2:
            partial.append({**item, "direction": "BULLISH" if bulls >= bears else "BEARISH"})
    return (sorted(cb, key=lambda x: x["prob"], reverse=True),
            sorted(cs, key=lambda x: x["prob"], reverse=True),
            sorted(partial, key=lambda x: x["count"], reverse=True)[:5],
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
# FORMAT TELEGRAM MESSAGES
# ─────────────────────────────────────────
def format_regular_message(session, market_summary, ai_analysis, bullish, bearish, snapshot):
    sess     = SESSIONS.get(session, SESSIONS["MORNING_BRIEFING"])
    now      = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    upcoming = snapshot.get("upcoming", [])
    lines    = [
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
        lines += ["\n🤖 *AI ANALYSIS — 3 PROMPT FRAMEWORK*\n", ai_analysis]
    else:
        lines.append("\n📊 *TECHNICAL SIGNALS*")
        if bullish:
            lines.append("🟢 *BULLISH:*")
            for s in bullish[:3]:
                div = "🔔" if s.get("bullish_div") else ""
                vol = "🔥" if s.get("vol_spike") else ""
                lines.append(
                    f"• *{s['symbol']}* {div}{vol} `{s['prob']}%` | Pattern: {s.get('pattern_rate','?')}%\n"
                    f"  Entry ₹{s['entry']} → 🎯 ₹{s['target']} (1:3) | SL ₹{s['sl']}\n"
                    f"  Support ₹{s.get('support','?')} | Resistance ₹{s.get('resistance','?')}"
                )
        if bearish:
            lines.append("🔴 *BEARISH:*")
            for s in bearish[:3]:
                div = "⚠️" if s.get("bearish_div") else ""
                vol = "🔥" if s.get("vol_spike") else ""
                lines.append(
                    f"• *{s['symbol']}* {div}{vol} `{s['prob']}%` | Pattern: {s.get('pattern_rate','?')}%\n"
                    f"  Entry ₹{s['entry']} → 🎯 ₹{s['target']} (1:3) | SL ₹{s['sl']}\n"
                    f"  Support ₹{s.get('support','?')} | Resistance ₹{s.get('resistance','?')}"
                )
        if not bullish and not bearish:
            lines.append("No strong signals — market uncertain today")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ _{sess['tip']}_",
        "⚠️ _Education only. Not SEBI advice. Use stop loss._",
        "🤖 _ViralVibe Stock Bot — Powered by MiniMax M2.5_",
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
    lines.append("_Sessions: BEST ENTRY | MIDDAY | POWER HOUR | CLOSING_")
    if cb:
        lines.append("\n✅ *CONFIRMED BUY — All sessions agreed*")
        for s in cb:
            lines.append(
                f"• *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`\n"
                f"  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}"
            )
    if cs:
        lines.append("\n✅ *CONFIRMED SELL — All sessions agreed*")
        for s in cs:
            lines.append(
                f"• *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`\n"
                f"  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}"
            )
    if not cb and not cs:
        lines.append("\nNo fully confirmed calls today")
    if partial:
        lines.append("\n⚠️ *PARTIAL SIGNALS*")
        for s in partial:
            icon = "🟢" if s.get("direction") == "BULLISH" else "🔴"
            lines.append(f"  {icon} *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`")
    if conflict:
        lines.append("\n❌ *CONFLICTING — SKIP*")
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
        print("⚠️ No Telegram credentials")
        print(message[:400])
        return
    for part in [message[i:i+4000] for i in range(0, len(message), 4000)]:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "Markdown"},
                timeout=15
            )
            print("  ✅ Sent!" if r.status_code == 200 else f"  ❌ {r.status_code}: {r.text[:80]}")
        except Exception as e:
            print(f"  ❌ {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run():
    global SESSION_LABEL

    # Auto-detect session from real IST time
    if SESSION_LABEL == "AUTO" or not SESSION_LABEL:
        SESSION_LABEL = detect_session_from_time()
        print(f"  ℹ️  Auto-detected session: {SESSION_LABEL}")

    print(f"\n{'='*55}")
    print(f"SESSION : {SESSION_LABEL}")
    print(f"TIME    : {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    print(f"AI      : MiniMax M2.5 Free via OpenRouter")
    print("="*55)

    clear_old_data()

    # Step 1 — Market snapshot
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

    # Step 2 — News
    print("\n[2] Fetching news headlines...")
    headlines = fetch_headlines(SESSION_LABEL)

    # Step 3 — Stock screening
    sess_config      = SESSIONS.get(SESSION_LABEL, SESSIONS["MORNING_BRIEFING"])
    bullish, bearish = [], []
    if sess_config["do_screen"]:
        print("\n[3] Screening stocks with pattern analysis...")
        bullish, bearish = screen_stocks()
    else:
        print("\n[3] Stock screening skipped for this session")

    # Step 4 — AI analysis
    print("\n[4] Getting AI analysis (MiniMax M2.5 free)...")
    ai_analysis = get_ai_analysis(
        SESSION_LABEL, headlines, market_summary, bullish, bearish
    )

    # Step 5 — Format and send
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

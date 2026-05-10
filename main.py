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
# CONFIG
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

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
    now_ist = datetime.now(IST)
    total   = now_ist.hour * 60 + now_ist.minute
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
        "title": "☀️ 8:00 AM — MORNING BRIEFING",
        "tip":   "Market opens in 1 hour. Prepare your watchlist now.",
        "do_screen": False,
    },
    "PRE_OPEN": {
        "title": "🕘 9:00 AM — PRE-OPEN ANALYSIS",
        "tip":   "Pre-open session running. Watch order book for direction.",
        "do_screen": False,
    },
    "MARKET_OPEN": {
        "title": "🔔 9:15 AM — MARKET OPEN",
        "tip":   "Highly volatile! Beginners avoid first 15 minutes.",
        "do_screen": True,
    },
    "BEST_ENTRY": {
        "title": "✅ 9:30 AM — BEST ENTRY WINDOW",
        "tip":   "Volatility settling. Best risk-reward window for beginners.",
        "do_screen": True,
    },
    "MIDDAY_REVIEW": {
        "title": "☀️ 12:00 PM — MIDDAY REVIEW",
        "tip":   "Low volume. Review open positions. Avoid new entries.",
        "do_screen": True,
    },
    "POWER_HOUR_PREP": {
        "title": "⚡ 2:00 PM — POWER HOUR PREP",
        "tip":   "Last 90 min. High liquidity returning. Square off by 3:20 PM!",
        "do_screen": True,
    },
    "CLOSING_ANALYSIS": {
        "title": "🔔 3:00 PM — CLOSING ANALYSIS",
        "tip":   "⚠️ Close ALL intraday positions by 3:20 PM!",
        "do_screen": False,
    },
    "EOD_SCORECARD": {
        "title": "📊 3:30 PM — END OF DAY SCORECARD",
        "tip":   "Market closed. Review the full day performance.",
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
            for h in data.get("CM",[]):
                dt = datetime.strptime(h.get("tradingDate",""), "%d-%b-%Y")
                holidays.append({"date":dt.strftime("%Y-%m-%d"),
                                 "description":h.get("description","Holiday"),
                                 "display":h.get("tradingDate","")})
            if holidays:
                return holidays
        except Exception:
            pass
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
    if not data: return {}
    result  = {}
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
    data = safe_nse_get("https://www.nseindia.com/api/fiidiiTradeReact")
    if data:
        result = []
        for row in data[:3]:
            fii = float(row.get("fiiNet",0) or 0)
            dii = float(row.get("diiNet",0) or 0)
            if fii != 0 or dii != 0:
                result.append({"date":row.get("date",""),"fii_net":fii,"dii_net":dii})
        if result:
            return result
    try:
        r = requests.get("https://trendlyne.com/macro-data/fii-dii/latest/snapshot-pastmonth/",
                         timeout=8, headers={"User-Agent":"Mozilla/5.0"})
        matches = re.findall(r'([+-]?[\d,]+\.?\d*)\s*Cr', r.text)
        if len(matches) >= 2:
            fii = float(matches[0].replace(",",""))
            dii = float(matches[1].replace(",",""))
            if fii != 0 or dii != 0:
                return [{"date":"latest","fii_net":fii,"dii_net":dii}]
    except Exception:
        pass
    return []

def fetch_market_data_yahoo():
    tickers = {
        "Nifty50":"^NSEI","Sensex":"^BSESN","BankNifty":"^NSEBANK",
        "NiftyIT":"^CNXIT","VIX":"^INDIAVIX","Crude":"CL=F","Gold":"GC=F",
        "USDINR":"INR=X","SP500":"^GSPC","Nasdaq":"^IXIC","Nikkei":"^N225",
    }
    result = {}
    for name, sym in tickers.items():
        try:
            t     = yf.Ticker(sym)
            info  = t.fast_info
            price = round(float(info.last_price), 2)
            prev  = round(float(info.previous_close), 2)
            chg   = round(((price-prev)/prev)*100, 2) if prev else 0
            result[name] = {"price":price,"change_pct":chg}
        except Exception:
            result[name] = {"price":0,"change_pct":0}
    return result

def get_market_snapshot():
    holidays       = fetch_nse_holidays()
    is_hol, reason = is_market_holiday(holidays)
    today          = datetime.now(IST)
    upcoming       = []
    for h in holidays:
        try:
            hdate = datetime.strptime(h["date"],"%Y-%m-%d").replace(tzinfo=IST)
            delta = (hdate - today).days
            if 0 < delta <= 7:
                upcoming.append({**h,"days_away":delta})
        except Exception:
            continue
    if is_hol:
        return {"is_holiday":True,"holiday_reason":reason,"upcoming":upcoming,
                "indices":{},"fii_dii":[],"yahoo":{}}
    return {"is_holiday":False,"holiday_reason":None,"upcoming":upcoming,
            "indices":fetch_nse_indices(),"fii_dii":fetch_fii_dii(),
            "yahoo":fetch_market_data_yahoo()}

def format_market_summary(snapshot):
    lines   = []
    yahoo   = snapshot.get("yahoo",{})
    indices = snapshot.get("indices",{})
    fii_dii = snapshot.get("fii_dii",[])
    def arrow(c): return "🟢" if c>0 else "🔴" if c<0 else "⚪"
    def yv(k):    return yahoo.get(k,{})
    for nkey, ykey, icon, label in [
        ("NIFTY 50","Nifty50","📊","Nifty50"),
        ("NIFTY BANK","BankNifty","🏦","BankNifty"),
        ("NIFTY IT","NiftyIT","💻","NiftyIT"),
        ("INDIA VIX","VIX","⚡","VIX"),
    ]:
        if indices.get(nkey):
            n = indices[nkey]
            lines.append(f"{icon} {label}: {n['last']} {arrow(n['pChange'])} {n['pChange']:+.2f}%")
        elif yv(ykey).get("price"):
            y = yv(ykey)
            lines.append(f"{icon} {label}: {y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")
    for k,icon,pre in [("Crude","🛢","$"),("Gold","🥇","$"),
                        ("SP500","🌏",""),("Nasdaq","💻",""),("Nikkei","🗾","")]:
        if yv(k).get("price"):
            y = yv(k)
            lines.append(f"{icon} {k}: {pre}{y['price']} {arrow(y['change_pct'])} {y['change_pct']:+.2f}%")
    if yv("USDINR").get("price"):
        lines.append(f"💵 USD/INR: ₹{yv('USDINR')['price']}")
    if fii_dii:
        l = fii_dii[0]
        fn,dn = float(l.get("fii_net",0)),float(l.get("dii_net",0))
        lines.append(
            f"🏦 FII: {'🟢 BOUGHT' if fn>0 else '🔴 SOLD'} ₹{abs(fn):.0f}Cr  "
            f"DII: {'🟢 BOUGHT' if dn>0 else '🔴 SOLD'} ₹{abs(dn):.0f}Cr  ({l.get('date','')})")
        if len(fii_dii)>=2:
            lines.append(f"   📈 FII trend: buying {sum(1 for d in fii_dii if float(d.get('fii_net',0))>0)}/{len(fii_dii)} days")
    else:
        lines.append("🏦 FII/DII: Updating — check NSE after 7 PM")
    return "\n".join(lines) if lines else "Market data loading..."

# ─────────────────────────────────────────
# TECHNICAL INDICATORS + PATTERN ANALYSIS
# ─────────────────────────────────────────
def rsi(s, p=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(p).mean()
    l = (-d.clip(upper=0)).rolling(p).mean()
    return 100 - (100/(1 + g/(l+1e-9)))

def macd_hist(s):
    m = s.ewm(span=12,adjust=False).mean() - s.ewm(span=26,adjust=False).mean()
    return m - m.ewm(span=9,adjust=False).mean()

def ema(s,p): return s.ewm(span=p,adjust=False).mean()

def vol_spike(vol,p=20):
    avg = vol.rolling(p).mean()
    return float(vol.iloc[-1]) > float(avg.iloc[-1])*1.5

def calc_prob(rv,hv,price,e50,e200,spike,direction):
    sc = 0
    if direction=="BULLISH":
        if rv<30: sc+=1.8
        elif rv<40: sc+=1.0
        elif rv<50: sc+=0.5
        if hv>0: sc+=1.2
        if price>e50: sc+=0.8
        if price>e200: sc+=1.0
        if spike: sc+=0.5
    else:
        if rv>70: sc+=1.8
        elif rv>60: sc+=1.0
        elif rv>50: sc+=0.5
        if hv<0: sc+=1.2
        if price<e50: sc+=0.8
        if price<e200: sc+=1.0
        if spike: sc+=0.5
    return min(round((sc/5.5)*100),97)

def get_extended_stock_data(symbol):
    """
    Gets extended 6-month data for pattern matching,
    support/resistance, volume profile analysis.
    Used for Prompt 1 and Prompt 2.
    """
    try:
        df = yf.download(symbol, period="6mo", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 50:
            return None

        close  = df["Close"].squeeze()
        high   = df["High"].squeeze()
        low    = df["Low"].squeeze()
        volume = df["Volume"].squeeze()
        price  = float(close.iloc[-1])

        # RSI
        rv    = rsi(close)
        curr_rsi = float(rv.iloc[-1])
        prev_rsi = float(rv.iloc[-5])  # 5 days ago

        # RSI divergence check
        price_higher = price > float(close.iloc[-5])
        rsi_lower    = curr_rsi < prev_rsi
        price_lower  = price < float(close.iloc[-5])
        rsi_higher   = curr_rsi > prev_rsi
        bearish_div  = price_higher and rsi_lower   # price up, RSI down = bearish divergence
        bullish_div  = price_lower and rsi_higher   # price down, RSI up = bullish divergence

        # Support/Resistance — recent swing highs and lows
        recent = close.tail(60)
        resistance = round(float(recent.nlargest(5).mean()), 2)
        support    = round(float(recent.nsmallest(5).mean()), 2)

        # Volume profile — high volume price zones
        avg_vol   = float(volume.mean())
        high_vol_days = volume[volume > avg_vol * 1.5]
        vol_price_zone = round(float(close[high_vol_days.index].mean()), 2) if len(high_vol_days) > 0 else price

        # ATR for stop loss calculation
        atr = float((high - low).rolling(14).mean().iloc[-1])

        # Historical pattern matching (last 3 similar RSI setups)
        patterns = []
        for i in range(20, len(close)-5):
            past_rsi = float(rv.iloc[i])
            if abs(past_rsi - curr_rsi) < 5:  # similar RSI
                past_price  = float(close.iloc[i])
                future_price = float(close.iloc[i+5])
                outcome = "UP" if future_price > past_price else "DOWN"
                change  = round(((future_price-past_price)/past_price)*100, 2)
                patterns.append({"outcome":outcome,"change":change,"rsi":round(past_rsi,1)})

        patterns = patterns[-3:] if len(patterns) >= 3 else patterns
        up_count = sum(1 for p in patterns if p["outcome"]=="UP")
        success_rate = round((up_count/len(patterns))*100) if patterns else 50

        # MACD
        h      = macd_hist(close)
        hv     = float(h.iloc[-1])
        hp     = float(h.iloc[-2])
        e50v   = float(ema(close,50).iloc[-1])
        e200v  = float(ema(close,200).iloc[-1])
        spike  = vol_spike(volume)
        cross  = (hv>0 and hp<=0) or (hv<0 and hp>=0)

        bp = calc_prob(curr_rsi, hv, price, e50v, e200v, spike, "BULLISH")
        sp = calc_prob(curr_rsi, hv, price, e50v, e200v, spike, "BEARISH")

        return {
            "symbol":        symbol.replace(".NS",""),
            "price":         price,
            "rsi":           round(curr_rsi,1),
            "atr":           round(atr,2),
            "support":       support,
            "resistance":    resistance,
            "vol_zone":      vol_price_zone,
            "bullish_div":   bullish_div,
            "bearish_div":   bearish_div,
            "patterns":      patterns,
            "success_rate":  success_rate,
            "ema50":         round(e50v,2),
            "ema200":        round(e200v,2),
            "vol_spike":     spike,
            "cross":         cross,
            "bull_prob":     bp,
            "bear_prob":     sp,
            "direction":     "BULLISH" if bp>=50 and bp>sp else "BEARISH" if sp>=50 and sp>bp else "NEUTRAL",
            "prob":          max(bp,sp),
            "entry_bull":    round(price,2),
            "target_bull":   round(price + atr*3, 2),  # 1:3 R:R
            "sl_bull":       round(price - atr,   2),
            "entry_bear":    round(price,2),
            "target_bear":   round(price - atr*3, 2),  # 1:3 R:R
            "sl_bear":       round(price + atr,   2),
        }
    except Exception as e:
        print(f"  Error {symbol}: {e}")
        return None

def screen_stocks():
    print(f"  Screening {len(ALL_STOCKS)} stocks...")
    stock_data = {}

    # Batch download
    try:
        print("  Batch downloading...")
        raw = yf.download(ALL_STOCKS, period="6mo", interval="1d",
                          progress=False, auto_adjust=True,
                          group_by="ticker", timeout=120)
        for sym in ALL_STOCKS:
            try:
                df = raw[sym].dropna() if isinstance(raw.columns,pd.MultiIndex) else raw.dropna()
                if len(df)>=50: stock_data[sym] = df
            except Exception:
                pass
        print(f"  ✅ Batch: {len(stock_data)} stocks")
    except Exception as e:
        print(f"  Batch failed: {e}")

    # Individual fallback
    missing = [s for s in ALL_STOCKS if s not in stock_data]
    if missing:
        print(f"  Individual: {len(missing)} remaining...")
        for i,sym in enumerate(missing):
            for attempt in range(2):
                try:
                    df = yf.download(sym,period="6mo",interval="1d",
                                     progress=False,auto_adjust=True,timeout=15)
                    if df is not None and len(df)>=50:
                        stock_data[sym] = df
                    break
                except Exception:
                    if attempt==0: time.sleep(random.uniform(1,3))
            if i%15==0 and i>0: time.sleep(random.uniform(1,2))

    print(f"  Total: {len(stock_data)} stocks")
    results = []

    for sym, df in stock_data.items():
        try:
            close  = df["Close"].squeeze()
            high   = df["High"].squeeze()
            low    = df["Low"].squeeze()
            volume = df["Volume"].squeeze()
            if len(close)<50: continue
            price  = float(close.iloc[-1])
            if price<=0: continue

            rv    = rsi(close)
            curr_rsi = float(rv.iloc[-1])
            prev_rsi = float(rv.iloc[-5])
            h     = macd_hist(close)
            hv    = float(h.iloc[-1])
            hp    = float(h.iloc[-2])
            e50v  = float(ema(close,50).iloc[-1])
            e200v = float(ema(close,200).iloc[-1])
            spk   = vol_spike(volume)
            crs   = (hv>0 and hp<=0) or (hv<0 and hp>=0)
            atr   = float((high-low).rolling(14).mean().iloc[-1])

            # RSI divergence
            bullish_div = price<float(close.iloc[-5]) and curr_rsi>prev_rsi
            bearish_div = price>float(close.iloc[-5]) and curr_rsi<prev_rsi

            # Support/Resistance
            recent     = close.tail(60)
            resistance = round(float(recent.nlargest(5).mean()),2)
            support    = round(float(recent.nsmallest(5).mean()),2)

            # Pattern success rate
            patterns = []
            for i in range(20, len(close)-5):
                if abs(float(rv.iloc[i])-curr_rsi)<5:
                    pp = float(close.iloc[i])
                    fp = float(close.iloc[i+5])
                    patterns.append("UP" if fp>pp else "DOWN")
            patterns   = patterns[-3:]
            up_count   = patterns.count("UP")
            srate      = round((up_count/len(patterns))*100) if patterns else 50

            bp = calc_prob(curr_rsi, hv, price, e50v, e200v, spk, "BULLISH")
            sp = calc_prob(curr_rsi, hv, price, e50v, e200v, spk, "BEARISH")
            name = sym.replace(".NS","")

            if bp>=50 and bp>sp:
                results.append({
                    "symbol":name,"direction":"BULLISH","prob":bp,
                    "entry":round(price,2),
                    "target":round(price+atr*3,2),   # 1:3 R:R
                    "sl":round(price-atr,2),
                    "rsi":round(curr_rsi,1),"vol_spike":spk,"cross":crs,
                    "support":support,"resistance":resistance,
                    "bullish_div":bullish_div,"bearish_div":bearish_div,
                    "pattern_success":srate,"atr":round(atr,2),
                    "ema50":round(e50v,2),"ema200":round(e200v,2),
                })
            elif sp>=50 and sp>bp:
                results.append({
                    "symbol":name,"direction":"BEARISH","prob":sp,
                    "entry":round(price,2),
                    "target":round(price-atr*3,2),   # 1:3 R:R
                    "sl":round(price+atr,2),
                    "rsi":round(curr_rsi,1),"vol_spike":spk,"cross":crs,
                    "support":support,"resistance":resistance,
                    "bullish_div":bullish_div,"bearish_div":bearish_div,
                    "pattern_success":srate,"atr":round(atr,2),
                    "ema50":round(e50v,2),"ema200":round(e200v,2),
                })
        except Exception as e:
            print(f"  Skipped {sym}: {e}")

    bullish = sorted([r for r in results if r["direction"]=="BULLISH"],
                     key=lambda x:x["prob"],reverse=True)[:5]
    bearish = sorted([r for r in results if r["direction"]=="BEARISH"],
                     key=lambda x:x["prob"],reverse=True)[:5]
    print(f"  ✅ Found: {len(bullish)} bullish, {len(bearish)} bearish")
    return bullish, bearish

# ─────────────────────────────────────────
# NEWS FETCHER
# ─────────────────────────────────────────
def fetch_headlines(session):
    feeds_map = {
        "MORNING_BRIEFING":[
            "https://news.google.com/rss/search?q=US+market+overnight+Asia+India+stocks&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=NSE+Nifty+India+stock+market+today&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=RBI+crude+oil+rupee+India&hl=en-IN&gl=IN&ceid=IN:en",
        ],
        "EOD_SCORECARD":[
            "https://news.google.com/rss/search?q=Sensex+Nifty+close+today+India&hl=en-IN&gl=IN&ceid=IN:en",
        ],
        "DEFAULT":[
            "https://news.google.com/rss/search?q=NSE+Nifty+Sensex+India+stock+market+today&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=FII+DII+India+market&hl=en-IN&gl=IN&ceid=IN:en",
            "https://news.google.com/rss/search?q=global+cues+crude+oil+rupee+India&hl=en-IN&gl=IN&ceid=IN:en",
        ],
    }
    feeds = feeds_map.get(session, feeds_map["DEFAULT"])
    all_h = []
    for url in feeds:
        try:
            r    = requests.get(url,timeout=10,headers={"User-Agent":"Mozilla/5.0"})
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
# CLAUDE AI — 3 PROMPT FRAMEWORK
# ─────────────────────────────────────────
def format_stock_details(stocks):
    """Format detailed stock data including all 3 prompt elements"""
    if not stocks:
        return "None found"
    lines = []
    for s in stocks[:3]:
        tags = []
        if s.get("bullish_div"): tags.append("🔔 BULLISH DIVERGENCE")
        if s.get("bearish_div"): tags.append("⚠️ BEARISH DIVERGENCE")
        if s.get("vol_spike"):   tags.append("🔥 VOL SPIKE")
        if s.get("cross"):       tags.append("⚡ MACD CROSS")

        lines.append(
            f"\n  {s['symbol']} | {s['direction']} | Prob: {s['prob']}%"
            f"\n  Price: ₹{s['entry']} | EMA50: ₹{s.get('ema50','N/A')} | EMA200: ₹{s.get('ema200','N/A')}"
            f"\n  Support: ₹{s.get('support','N/A')} | Resistance: ₹{s.get('resistance','N/A')}"
            f"\n  RSI: {s['rsi']} | ATR: ₹{s.get('atr','N/A')}"
            f"\n  Pattern success (last 3 similar): {s.get('pattern_success','N/A')}%"
            f"\n  Entry: ₹{s['entry']} | Target: ₹{s['target']} (1:3 R:R) | SL: ₹{s['sl']}"
            + (f"\n  Signals: {' | '.join(tags)}" if tags else "")
        )
    return "\n".join(lines)

def get_claude_analysis(session, headlines, market_summary, bullish, bearish):
    if not ANTHROPIC_API_KEY:
        return None

    today    = datetime.now(IST).strftime("%d %b %Y %A")
    time_now = datetime.now(IST).strftime("%I:%M %p")
    news_str = "\n".join([f"- {h}" for h in headlines[:15]])
    bull_str = format_stock_details(bullish)
    bear_str = format_stock_details(bearish)

    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    prev_ctx  = ""
    for label in TRACKING_SESSIONS:
        path = DATA_DIR/f"session_{label}.json"
        if path.exists():
            try:
                with open(path) as f:
                    d = json.load(f)
                if d.get("date")==today_str:
                    prev_ctx += f"\n{label}: {len(d.get('bullish',[]))} bullish, {len(d.get('bearish',[]))} bearish"
            except Exception:
                pass

    # ═══════════════════════════════════════════
    # THE 3-PROMPT FRAMEWORK INTEGRATED INTO ONE
    # ═══════════════════════════════════════════
    prompt = f"""You are a senior professional Indian stock market analyst.
Today: {today} | Time: {time_now} IST | Session: {session}

MARKET DATA:
{market_summary}

NEWS:
{news_str}

BULLISH STOCK SIGNALS (with full technical data):
{bull_str}

BEARISH STOCK SIGNALS (with full technical data):
{bear_str}

PREVIOUS SESSIONS:{prev_ctx or ' First session of day'}

Provide analysis using ALL THREE frameworks below:

━━ PROMPT 1 — CHART ANALYSIS ━━
For each top stock signal, analyze using:
- Support & Resistance levels (use the data provided)
- Volume profile (high volume zones = strong support/resistance)
- RSI divergence (flag any divergence signals)

Give 3 scenarios per top stock:
BULLISH SCENARIO: Entry ₹[x] | Target ₹[x] | Condition: [what must happen]
BEARISH SCENARIO: Entry ₹[x] | Target ₹[x] | Condition: [what must happen]
NEUTRAL SCENARIO: Range [x]–[x] | What to watch for breakout direction

━━ PROMPT 2 — PATTERN HISTORY ━━
For each top stock:
- Last 3 similar RSI patterns in past 6 months → what happened after
- Pattern success rate: [X]% bullish outcome
- Based on history: [recommended action]

━━ PROMPT 3 — RISK MANAGER ━━
For each trade call, apply 2% account risk rule:
Assuming account size: ₹1,00,000 (user can adjust)
- 2% risk = ₹2,000 max loss per trade
- Position size = ₹2,000 ÷ (Entry - SL) = [X shares/units]
- Maintain 1:3 Risk:Reward ratio
- Stop Loss: ₹[x] | Take Profit 1: ₹[x] | Take Profit 2: ₹[x]

Format output as:
MARKET BIAS: [BULLISH/BEARISH/SIDEWAYS] | CONFIDENCE: [HIGH/MEDIUM/LOW]
STRATEGY: [Buy on Dips/Sell on Rise/Avoid]

Then for top 2-3 stocks — apply all 3 prompts above.

End with:
KEY LEVELS: Nifty Support [x]/[x] | Resistance [x]/[x]
RISK REMINDER: [one line]
CONFIDENCE: [HIGH/MEDIUM/LOW] | BIAS: [BULLISH/BEARISH/SIDEWAYS]

Keep total under 600 words. Be specific with numbers."""

    try:
        print("  Calling Claude AI (3-prompt framework)...")
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key":ANTHROPIC_API_KEY,
                     "anthropic-version":"2023-06-01",
                     "content-type":"application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":1400,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=40
        )
        if res.status_code==200:
            print("  ✅ Claude done")
            return res.json()["content"][0]["text"]
        print(f"  ❌ Claude: {res.status_code}")
        return None
    except Exception as e:
        print(f"  ❌ Claude: {e}")
        return None

# ─────────────────────────────────────────
# SESSION DATA
# ─────────────────────────────────────────
def save_session(label, bullish, bearish):
    today = datetime.now(IST).strftime("%Y-%m-%d")
    with open(DATA_DIR/f"session_{label}.json","w") as f:
        json.dump({"session":label,"date":today,
                   "time":datetime.now(IST).strftime("%H:%M"),
                   "bullish":bullish,"bearish":bearish},f,indent=2)

def load_all_sessions():
    today, sessions = datetime.now(IST).strftime("%Y-%m-%d"), {}
    for label in TRACKING_SESSIONS:
        path = DATA_DIR/f"session_{label}.json"
        if path.exists():
            with open(path) as f: d=json.load(f)
            if d.get("date")==today: sessions[label]=d
    return sessions

def build_scorecard(sessions):
    tracker={}
    for label,data in sessions.items():
        for s in data.get("bullish",[])+data.get("bearish",[]):
            sym=s["symbol"]
            if sym not in tracker:
                tracker[sym]={"sessions":{},"probs":[],
                              "entry":s["entry"],"target":s["target"],"sl":s["sl"]}
            tracker[sym]["sessions"][label]=s["direction"]
            tracker[sym]["probs"].append(s["prob"])
    total=len(sessions)
    cb,cs,partial,conflict=[],[],[],[]
    for sym,info in tracker.items():
        dirs=list(info["sessions"].values())
        bulls=dirs.count("BULLISH"); bears=dirs.count("BEARISH"); count=len(dirs)
        avg_p=round(sum(info["probs"])/len(info["probs"]))
        dots="".join("🟢" if info["sessions"].get(l)=="BULLISH"
                     else "🔴" if info["sessions"].get(l)=="BEARISH" else "⚪"
                     for l in TRACKING_SESSIONS)
        item={"symbol":sym,"count":count,"total":total,"prob":avg_p,"dots":dots,
              "entry":info["entry"],"target":info["target"],"sl":info["sl"]}
        if bulls>0 and bears>0: conflict.append(item)
        elif count==total:
            cb.append({**item,"direction":"BULLISH"}) if bulls==total \
            else cs.append({**item,"direction":"BEARISH"})
        elif count>=2:
            partial.append({**item,"direction":"BULLISH" if bulls>=bears else "BEARISH"})
    return (sorted(cb,key=lambda x:x["prob"],reverse=True),
            sorted(cs,key=lambda x:x["prob"],reverse=True),
            sorted(partial,key=lambda x:x["count"],reverse=True)[:5],
            conflict[:4])

def clear_old_data():
    today=datetime.now(IST).strftime("%Y-%m-%d")
    for path in DATA_DIR.glob("session_*.json"):
        try:
            with open(path) as f: d=json.load(f)
            if d.get("date")!=today: path.unlink()
        except Exception: path.unlink()

# ─────────────────────────────────────────
# FORMAT MESSAGES
# ─────────────────────────────────────────
def format_regular_message(session, market_summary, ai_analysis, bullish, bearish, snapshot):
    sess     = SESSIONS.get(session,SESSIONS["MORNING_BRIEFING"])
    now      = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    upcoming = snapshot.get("upcoming",[])
    lines    = [
        "📊 *VIRALVIBE STOCK BOT*",
        f"*{sess['title']}*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n{market_summary}",
    ]
    if upcoming and upcoming[0]["days_away"]<=2:
        h=upcoming[0]
        lines.append(f"\n⚠️ *Holiday Alert:* {h['description']} — {h['display']} ({h['days_away']} day away)")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━")
    if ai_analysis:
        lines+=["🤖 *AI ANALYSIS — 3 PROMPT FRAMEWORK*\n",ai_analysis]
    else:
        lines.append("\n📊 *TECHNICAL SIGNALS*")
        if bullish:
            lines.append("🟢 *BULLISH:*")
            for s in bullish[:3]:
                div="🔔" if s.get("bullish_div") else ""
                vol="🔥" if s.get("vol_spike") else ""
                lines.append(
                    f"• *{s['symbol']}* {div}{vol} `{s['prob']}%` | Pattern: {s.get('pattern_success','?')}%\n"
                    f"  Entry ₹{s['entry']} → 🎯 ₹{s['target']} (1:3) | SL ₹{s['sl']}\n"
                    f"  Support ₹{s.get('support','?')} | Resistance ₹{s.get('resistance','?')}"
                )
        if bearish:
            lines.append("🔴 *BEARISH:*")
            for s in bearish[:3]:
                div="⚠️" if s.get("bearish_div") else ""
                vol="🔥" if s.get("vol_spike") else ""
                lines.append(
                    f"• *{s['symbol']}* {div}{vol} `{s['prob']}%` | Pattern: {s.get('pattern_success','?')}%\n"
                    f"  Entry ₹{s['entry']} → 🎯 ₹{s['target']} (1:3) | SL ₹{s['sl']}\n"
                    f"  Support ₹{s.get('support','?')} | Resistance ₹{s.get('resistance','?')}"
                )
        if not bullish and not bearish:
            lines.append("No strong signals — market uncertain")
    lines+=[
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"⏰ _{sess['tip']}_",
        "⚠️ _Education only. Not SEBI advice. Use stop loss._",
        "🤖 _ViralVibe Stock Bot_",
    ]
    return "\n".join(lines)

def format_eod_scorecard(cb,cs,partial,conflict,ai_analysis,market_summary):
    now=datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    lines=[
        "📊 *VIRALVIBE — END OF DAY SCORECARD*",
        f"📅 {now}","━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n{market_summary}","\n━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if ai_analysis: lines+=["🤖 *AI EOD ANALYSIS*\n",ai_analysis,"\n━━━━━━━━━━━━━━━━━━━━━━━━━"]
    lines.append("\n🏆 *ALL-DAY CONSISTENCY SCORECARD*")
    if cb:
        lines.append("\n✅ *CONFIRMED BUY*")
        for s in cb:
            lines.append(f"• *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`\n  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
    if cs:
        lines.append("\n✅ *CONFIRMED SELL*")
        for s in cs:
            lines.append(f"• *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`\n  Entry ₹{s['entry']} → 🎯 ₹{s['target']}  SL ₹{s['sl']}")
    if not cb and not cs: lines.append("\nNo confirmed calls today")
    if partial:
        lines.append("\n⚠️ *PARTIAL*")
        for s in partial:
            icon="🟢" if s.get("direction")=="BULLISH" else "🔴"
            lines.append(f"  {icon} *{s['symbol']}* {s['dots']} ({s['count']}/{s['total']}) `{s['prob']}%`")
    if conflict:
        lines.append("\n❌ *CONFLICTING — SKIP*")
        for s in conflict: lines.append(f"  ⚠️ *{s['symbol']}* {s['dots']}")
    lines+=["\n━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🌙 _See you tomorrow!_",
            "⚠️ _Education only. Not SEBI advice._","🤖 _ViralVibe Stock Bot_"]
    return "\n".join(lines)

def format_holiday_message(reason,upcoming):
    now=datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    lines=["📅 *VIRALVIBE STOCK BOT*",f"🗓 {now}","━━━━━━━━━━━━━━━━━━━━━━━━━",
           f"\n🏖 *Market Holiday: {reason}*","NSE & BSE closed today."]
    if upcoming:
        lines.append("\n📅 *Upcoming:*")
        for h in upcoming[:3]: lines.append(f"  • {h['display']} — {h['description']} ({h['days_away']} days)")
    lines+=["💡 Review portfolio, study charts, plan tomorrow.",
            "\n🤖 _ViralVibe Stock Bot — Back next trading day!_"]
    return "\n".join(lines)

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ No credentials"); print(message[:400]); return
    for part in [message[i:i+4000] for i in range(0,len(message),4000)]:
        try:
            r=requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id":TELEGRAM_CHAT_ID,"text":part,"parse_mode":"Markdown"},
                timeout=15)
            print("  ✅ Sent!" if r.status_code==200 else f"  ❌ {r.status_code}")
        except Exception as e: print(f"  ❌ {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run():
    global SESSION_LABEL
    if SESSION_LABEL=="AUTO" or not SESSION_LABEL:
        SESSION_LABEL=detect_session_from_time()
        print(f"  ℹ️  Auto-detected: {SESSION_LABEL}")

    print(f"\n{'='*55}")
    print(f"SESSION : {SESSION_LABEL}")
    print(f"TIME    : {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    print("="*55)

    clear_old_data()

    print("\n[1] Market snapshot...")
    snapshot=get_market_snapshot()
    if snapshot["is_holiday"]:
        reason=snapshot["holiday_reason"]; upcoming=snapshot["upcoming"]
        print(f"  🏖 Holiday: {reason}")
        if SESSION_LABEL in ["MORNING_BRIEFING","BEST_ENTRY"]:
            send_telegram(format_holiday_message(reason,upcoming))
        else: print("  Skipping duplicate")
        return

    print("  ✅ Market open")
    market_summary=format_market_summary(snapshot)

    print("\n[2] Fetching headlines...")
    headlines=fetch_headlines(SESSION_LABEL)

    sess_config=SESSIONS.get(SESSION_LABEL,SESSIONS["MORNING_BRIEFING"])
    bullish,bearish=[],[]
    if sess_config["do_screen"]:
        print("\n[3] Screening stocks (with pattern analysis)...")
        bullish,bearish=screen_stocks()
    else:
        print("\n[3] Skipping screen for this session")

    print("\n[4] Getting Claude AI (3-prompt framework)...")
    ai_analysis=get_claude_analysis(SESSION_LABEL,headlines,market_summary,bullish,bearish)

    print("\n[5] Sending to Telegram...")
    if SESSION_LABEL=="EOD_SCORECARD":
        sessions=load_all_sessions()
        cb,cs,partial,conflict=build_scorecard(sessions)
        msg=format_eod_scorecard(cb,cs,partial,conflict,ai_analysis,market_summary)
    else:
        if SESSION_LABEL in TRACKING_SESSIONS:
            save_session(SESSION_LABEL,bullish,bearish)
        msg=format_regular_message(SESSION_LABEL,market_summary,ai_analysis,
                                   bullish,bearish,snapshot)
    send_telegram(msg)
    print("\n✅ All done!")

if __name__ == "__main__":
    run()

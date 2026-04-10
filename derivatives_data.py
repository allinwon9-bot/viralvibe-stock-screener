import requests
import json
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(NSE_HEADERS)

def init_session():
    try:
        SESSION.get("https://www.nseindia.com", timeout=10)
        SESSION.get("https://www.nseindia.com/option-chain", timeout=10)
        return True
    except Exception as e:
        print(f"  NSE session init failed: {e}")
        return False

# ─────────────────────────────────────────
# OPTION CHAIN — NIFTY & BANK NIFTY
# ─────────────────────────────────────────
def fetch_option_chain(symbol="NIFTY"):
    """
    Fetches full option chain for NIFTY or BANKNIFTY.
    Returns PCR, max pain, OI buildup summary.
    """
    try:
        init_session()
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        r   = SESSION.get(url, timeout=15)

        if r.status_code != 200:
            print(f"  ❌ Option chain {symbol}: {r.status_code}")
            return None

        data       = r.json()
        records    = data.get("records", {})
        filtered   = data.get("filtered", {})
        spot_price = float(records.get("underlyingValue", 0))
        expiry_dates = records.get("expiryDates", [])
        nearest_expiry = expiry_dates[0] if expiry_dates else "N/A"

        # Get near ATM strikes (spot ± 500 for Nifty, ± 1000 for BankNifty)
        range_val  = 1000 if symbol == "BANKNIFTY" else 500
        chain_data = filtered.get("data", [])

        total_call_oi = 0
        total_put_oi  = 0
        total_call_chg = 0
        total_put_chg  = 0

        call_oi_by_strike = {}
        put_oi_by_strike  = {}
        max_pain_data     = {}

        for item in chain_data:
            strike = item.get("strikePrice", 0)
            ce     = item.get("CE", {})
            pe     = item.get("PE", {})

            ce_oi  = ce.get("openInterest", 0) or 0
            pe_oi  = pe.get("openInterest", 0) or 0
            ce_chg = ce.get("changeinOpenInterest", 0) or 0
            pe_chg = pe.get("changeinOpenInterest", 0) or 0

            total_call_oi  += ce_oi
            total_put_oi   += pe_oi
            total_call_chg += ce_chg
            total_put_chg  += pe_chg

            call_oi_by_strike[strike] = ce_oi
            put_oi_by_strike[strike]  = pe_oi

            # For max pain calculation
            max_pain_data[strike] = {"ce_oi": ce_oi, "pe_oi": pe_oi}

        # PCR
        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

        # Max Call OI (resistance) and Max Put OI (support)
        max_call_strike = max(call_oi_by_strike, key=call_oi_by_strike.get) if call_oi_by_strike else 0
        max_put_strike  = max(put_oi_by_strike,  key=put_oi_by_strike.get)  if put_oi_by_strike  else 0

        # Top 3 call and put OI strikes
        top_calls = sorted(call_oi_by_strike.items(), key=lambda x: x[1], reverse=True)[:3]
        top_puts  = sorted(put_oi_by_strike.items(),  key=lambda x: x[1], reverse=True)[:3]

        # Max Pain calculation
        max_pain = calculate_max_pain(max_pain_data)

        # OI interpretation
        call_oi_change_pct = round((total_call_chg / total_call_oi * 100), 2) if total_call_oi > 0 else 0
        put_oi_change_pct  = round((total_put_chg  / total_put_oi  * 100), 2) if total_put_oi  > 0 else 0

        result = {
            "symbol":          symbol,
            "spot":            spot_price,
            "expiry":          nearest_expiry,
            "pcr":             pcr,
            "pcr_signal":      interpret_pcr(pcr),
            "max_pain":        max_pain,
            "total_call_oi":   total_call_oi,
            "total_put_oi":    total_put_oi,
            "call_oi_chg":     total_call_chg,
            "put_oi_chg":      total_put_chg,
            "call_oi_chg_pct": call_oi_change_pct,
            "put_oi_chg_pct":  put_oi_change_pct,
            "max_call_strike": max_call_strike,
            "max_put_strike":  max_put_strike,
            "top_calls":       top_calls,
            "top_puts":        top_puts,
            "oi_signal":       interpret_oi_buildup(total_call_chg, total_put_chg),
        }

        print(f"  ✅ {symbol} options: PCR={pcr}, MaxPain={max_pain}, Resistance={max_call_strike}, Support={max_put_strike}")
        return result

    except Exception as e:
        print(f"  ❌ Option chain {symbol} failed: {e}")
        return None

def calculate_max_pain(data):
    """Max pain = strike where total OI loss is minimum"""
    try:
        min_pain  = float('inf')
        max_pain  = 0
        for target_strike in data.keys():
            total_loss = 0
            for strike, oi in data.items():
                # Call writers lose if spot > strike
                call_loss = max(0, target_strike - strike) * oi.get("ce_oi", 0)
                # Put writers lose if spot < strike
                put_loss  = max(0, strike - target_strike) * oi.get("pe_oi", 0)
                total_loss += call_loss + put_loss
            if total_loss < min_pain:
                min_pain = total_loss
                max_pain = target_strike
        return max_pain
    except Exception:
        return 0

def interpret_pcr(pcr):
    if pcr >= 1.5:   return "STRONGLY BULLISH (oversold, put heavy)"
    elif pcr >= 1.2: return "BULLISH (more put writing = support)"
    elif pcr >= 0.9: return "NEUTRAL"
    elif pcr >= 0.7: return "BEARISH (more call writing = resistance)"
    else:            return "STRONGLY BEARISH (call heavy)"

def interpret_oi_buildup(call_chg, put_chg):
    if put_chg > 0 and call_chg > 0:
        if put_chg > call_chg:   return "BULLISH — More put writing (support building)"
        else:                     return "BEARISH — More call writing (resistance building)"
    elif put_chg > 0 and call_chg < 0:
        return "BULLISH — Put writing + call unwinding"
    elif put_chg < 0 and call_chg > 0:
        return "BEARISH — Call writing + put unwinding"
    else:
        return "NEUTRAL — Mixed OI changes"

# ─────────────────────────────────────────
# FII DERIVATIVES DATA
# ─────────────────────────────────────────
def fetch_fii_derivatives():
    """Fetches FII activity in F&O segment"""
    try:
        init_session()
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        r   = SESSION.get(url, timeout=10)

        if r.status_code != 200:
            return {}

        data   = r.json()
        result = {"cash": [], "fno": []}

        for row in data[:5]:
            result["cash"].append({
                "date":     row.get("date",""),
                "fii_net":  row.get("fiiNet", 0),
                "dii_net":  row.get("diiNet", 0),
            })

        # Try to get F&O specific data
        url2 = "https://www.nseindia.com/api/fii-stats"
        r2   = SESSION.get(url2, timeout=10)
        if r2.status_code == 200:
            fno_data = r2.json()
            for item in fno_data.get("data", [])[:3]:
                result["fno"].append({
                    "date":           item.get("date",""),
                    "index_fut_net":  item.get("indexFutNet", 0),
                    "index_opt_net":  item.get("indexOptNet", 0),
                    "stock_fut_net":  item.get("stockFutNet", 0),
                    "stock_opt_net":  item.get("stockOptNet", 0),
                })

        print(f"  ✅ FII data: {len(result['cash'])} cash days, {len(result['fno'])} F&O days")
        return result

    except Exception as e:
        print(f"  ❌ FII derivatives failed: {e}")
        return {}

# ─────────────────────────────────────────
# FUTURES OI & BUILDUP
# ─────────────────────────────────────────
def fetch_futures_data(symbol="NIFTY"):
    """Fetches futures OI and price data to identify buildup patterns"""
    try:
        init_session()
        url = f"https://www.nseindia.com/api/quote-derivative?symbol={symbol}"
        r   = SESSION.get(url, timeout=10)

        if r.status_code != 200:
            return {}

        data    = r.json()
        fut_data = []

        for item in data.get("stocks", []):
            meta = item.get("metadata", {})
            if meta.get("instrumentType") == "Index Futures":
                oi      = meta.get("openInterest", 0)
                chg_oi  = meta.get("changeinOpenInterest", 0)
                ltp     = meta.get("lastPrice", 0)
                chg_pct = meta.get("pChange", 0)
                expiry  = meta.get("expiryDate", "")

                if oi > 0:
                    buildup = interpret_futures_buildup(chg_pct, chg_oi)
                    fut_data.append({
                        "expiry":  expiry,
                        "ltp":     ltp,
                        "oi":      oi,
                        "chg_oi":  chg_oi,
                        "chg_pct": chg_pct,
                        "buildup": buildup,
                    })

        # Sort by nearest expiry
        fut_data.sort(key=lambda x: x.get("expiry", ""))

        print(f"  ✅ {symbol} futures: {len(fut_data)} contracts")
        return {"symbol": symbol, "contracts": fut_data[:3]}

    except Exception as e:
        print(f"  ❌ Futures {symbol} failed: {e}")
        return {}

def interpret_futures_buildup(price_chg, oi_chg):
    """Classic 4-way futures interpretation"""
    if price_chg > 0 and oi_chg > 0:
        return "🟢 LONG BUILDUP (Bullish — fresh longs)"
    elif price_chg > 0 and oi_chg < 0:
        return "🟡 SHORT COVERING (Cautiously Bullish)"
    elif price_chg < 0 and oi_chg > 0:
        return "🔴 SHORT BUILDUP (Bearish — fresh shorts)"
    elif price_chg < 0 and oi_chg < 0:
        return "🟠 LONG UNWINDING (Bearish — longs exiting)"
    else:
        return "⚪ NEUTRAL"

# ─────────────────────────────────────────
# INDIA VIX
# ─────────────────────────────────────────
def fetch_vix():
    """Fetches India VIX current value and interpretation"""
    try:
        init_session()
        url = "https://www.nseindia.com/api/allIndices"
        r   = SESSION.get(url, timeout=10)

        if r.status_code != 200:
            return {}

        data = r.json()
        for item in data.get("data", []):
            if item.get("index") == "INDIA VIX":
                vix     = float(item.get("last", 0))
                chg     = float(item.get("change", 0))
                chg_pct = float(item.get("percentChange", 0))
                return {
                    "vix":       vix,
                    "change":    chg,
                    "chg_pct":   chg_pct,
                    "signal":    interpret_vix(vix, chg_pct),
                    "implication": vix_implication(vix),
                }
        return {}

    except Exception as e:
        print(f"  ❌ VIX failed: {e}")
        return {}

def interpret_vix(vix, chg_pct):
    if vix > 25:
        direction = "Rising" if chg_pct > 0 else "Falling"
        return f"HIGH FEAR ({direction}) — Expect sharp moves"
    elif vix > 18:
        direction = "Rising" if chg_pct > 0 else "Falling"
        return f"ELEVATED ({direction}) — Cautious trading"
    elif vix > 12:
        return "NORMAL — Steady market conditions"
    else:
        return "LOW — Complacency risk, potential reversal"

def vix_implication(vix):
    if vix > 25:   return "Option premiums expensive. Buy options risky. Better to sell spreads."
    elif vix > 18: return "Options fairly priced. Directional plays viable with strict SL."
    elif vix > 12: return "Options cheap. Good time to buy options for momentum trades."
    else:          return "Options very cheap. Buy options aggressively on breakouts."

# ─────────────────────────────────────────
# FULL DERIVATIVES SNAPSHOT
# ─────────────────────────────────────────
def get_derivatives_snapshot():
    """Returns complete derivatives data for analysis"""
    print("  Fetching derivatives snapshot...")

    nifty_options   = fetch_option_chain("NIFTY")
    banknifty_options = fetch_option_chain("BANKNIFTY")
    nifty_futures   = fetch_futures_data("NIFTY")
    banknifty_futures = fetch_futures_data("BANKNIFTY")
    fii_data        = fetch_fii_derivatives()
    vix_data        = fetch_vix()

    return {
        "nifty_options":      nifty_options,
        "banknifty_options":  banknifty_options,
        "nifty_futures":      nifty_futures,
        "banknifty_futures":  banknifty_futures,
        "fii_data":           fii_data,
        "vix":                vix_data,
        "timestamp":          datetime.now(IST).strftime("%d %b %Y %H:%M IST"),
    }

# ─────────────────────────────────────────
# FORMAT FOR CLAUDE PROMPT
# ─────────────────────────────────────────
def format_derivatives_for_prompt(snap):
    lines = []

    # VIX
    vix = snap.get("vix", {})
    if vix:
        lines.append(f"INDIA VIX: {vix.get('vix')} ({vix.get('chg_pct',0):+.2f}%)")
        lines.append(f"VIX Signal: {vix.get('signal','')}")
        lines.append(f"VIX Implication: {vix.get('implication','')}")

    lines.append("")

    # Nifty Options
    no = snap.get("nifty_options")
    if no:
        lines.append(f"NIFTY OPTIONS (Expiry: {no.get('expiry','N/A')})")
        lines.append(f"  Spot: {no.get('spot')}")
        lines.append(f"  PCR: {no.get('pcr')} — {no.get('pcr_signal','')}")
        lines.append(f"  Max Pain: {no.get('max_pain')}")
        lines.append(f"  Max Call OI (Resistance): {no.get('max_call_strike')} ({no.get('total_call_oi',0):,} OI)")
        lines.append(f"  Max Put OI (Support): {no.get('max_put_strike')} ({no.get('total_put_oi',0):,} OI)")
        lines.append(f"  Call OI Change: {no.get('call_oi_chg_pct',0):+.1f}%  Put OI Change: {no.get('put_oi_chg_pct',0):+.1f}%")
        lines.append(f"  OI Signal: {no.get('oi_signal','')}")
        top_c = no.get("top_calls",[])
        top_p = no.get("top_puts",[])
        if top_c:
            lines.append(f"  Top Call Strikes: {', '.join([f'{s}({o:,})' for s,o in top_c])}")
        if top_p:
            lines.append(f"  Top Put Strikes: {', '.join([f'{s}({o:,})' for s,o in top_p])}")

    lines.append("")

    # Bank Nifty Options
    bno = snap.get("banknifty_options")
    if bno:
        lines.append(f"BANK NIFTY OPTIONS (Expiry: {bno.get('expiry','N/A')})")
        lines.append(f"  Spot: {bno.get('spot')}")
        lines.append(f"  PCR: {bno.get('pcr')} — {bno.get('pcr_signal','')}")
        lines.append(f"  Max Pain: {bno.get('max_pain')}")
        lines.append(f"  Max Call OI (Resistance): {bno.get('max_call_strike')}")
        lines.append(f"  Max Put OI (Support): {bno.get('max_put_strike')}")
        lines.append(f"  OI Signal: {bno.get('oi_signal','')}")

    lines.append("")

    # Futures
    nf = snap.get("nifty_futures", {})
    if nf.get("contracts"):
        lines.append("NIFTY FUTURES:")
        for c in nf["contracts"][:2]:
            lines.append(f"  {c.get('expiry','')}: LTP {c.get('ltp')} | OI {c.get('oi',0):,} | ChgOI {c.get('chg_oi',0):+,} | {c.get('buildup','')}")

    bnf = snap.get("banknifty_futures", {})
    if bnf.get("contracts"):
        lines.append("BANK NIFTY FUTURES:")
        for c in bnf["contracts"][:2]:
            lines.append(f"  {c.get('expiry','')}: LTP {c.get('ltp')} | OI {c.get('oi',0):,} | ChgOI {c.get('chg_oi',0):+,} | {c.get('buildup','')}")

    lines.append("")

    # FII F&O
    fii = snap.get("fii_data", {})
    cash = fii.get("cash", [])
    fno  = fii.get("fno", [])
    if cash:
        latest = cash[0]
        fii_net = float(latest.get("fii_net", 0))
        dii_net = float(latest.get("dii_net", 0))
        lines.append(f"FII/DII CASH ({latest.get('date','')}):")
        lines.append(f"  FII: {'BOUGHT' if fii_net>0 else 'SOLD'} ₹{abs(fii_net):.0f} Cr")
        lines.append(f"  DII: {'BOUGHT' if dii_net>0 else 'SOLD'} ₹{abs(dii_net):.0f} Cr")
        # 5 day trend
        fii_buying_days = sum(1 for d in cash if float(d.get("fii_net",0)) > 0)
        lines.append(f"  FII 5-day trend: Buying {fii_buying_days}/5 days")
    if fno:
        latest = fno[0]
        lines.append(f"FII F&O ({latest.get('date','')}):")
        lines.append(f"  Index Futures Net: ₹{float(latest.get('index_fut_net',0)):.0f} Cr")
        lines.append(f"  Index Options Net: ₹{float(latest.get('index_opt_net',0)):.0f} Cr")
        lines.append(f"  Stock Futures Net: ₹{float(latest.get('stock_fut_net',0)):.0f} Cr")

    return "\n".join(lines)


if __name__ == "__main__":
    print("Testing derivatives fetcher...")
    snap = get_derivatives_snapshot()
    print("\n" + format_derivatives_for_prompt(snap))

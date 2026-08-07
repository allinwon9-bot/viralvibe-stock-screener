import requests
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

# ─────────────────────────────────────────
# NSE HEADERS — required to avoid blocking
# ─────────────────────────────────────────
NSE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}

NSE_SESSION = requests.Session()
NSE_SESSION.headers.update(NSE_HEADERS)

# ─────────────────────────────────────────
# INIT NSE SESSION (required for cookies)
# ─────────────────────────────────────────
def init_nse_session():
    try:
        NSE_SESSION.get("https://www.nseindia.com", timeout=10)
        return True
    except Exception as e:
        print(f"  NSE session init failed: {e}")
        return False

# ─────────────────────────────────────────
# FETCH NSE HOLIDAYS
# ─────────────────────────────────────────
def fetch_nse_holidays():
    """
    Fetches official NSE holiday list for current year.
    Returns list of holiday dicts with date and description.
    """
    try:
        init_nse_session()
        url = "https://www.nseindia.com/api/holiday-master?type=trading"
        r   = NSE_SESSION.get(url, timeout=10)

        if r.status_code == 200:
            data     = r.json()
            holidays = []

            # NSE returns holidays by segment
            # We use CM (Capital Market) segment
            cm_holidays = data.get("CM", [])

            for h in cm_holidays:
                # NSE date format: "08-Jan-2026"
                try:
                    date_str = h.get("tradingDate", "")
                    desc     = h.get("description", "Holiday")
                    day      = h.get("day", "")
                    dt       = datetime.strptime(date_str, "%d-%b-%Y")
                    holidays.append({
                        "date":        dt.strftime("%Y-%m-%d"),
                        "description": desc,
                        "day":         day,
                        "display":     date_str
                    })
                except Exception:
                    continue

            print(f"  ✅ Fetched {len(holidays)} NSE holidays")
            return holidays
        else:
            print(f"  ❌ NSE holidays error: {r.status_code}")
            return get_fallback_holidays()

    except Exception as e:
        print(f"  ❌ NSE holidays failed: {e}")
        return get_fallback_holidays()

# ─────────────────────────────────────────
# FALLBACK HOLIDAY LIST (2026)
# In case NSE API is unavailable
# ─────────────────────────────────────────
def get_fallback_holidays():
    raw = [
        {"date": "2026-01-26", "description": "Republic Day",         "day": "Monday"},
        {"date": "2026-02-26", "description": "Mahashivratri",        "day": "Thursday"},
        {"date": "2026-03-25", "description": "Holi",                 "day": "Wednesday"},
        {"date": "2026-04-01", "description": "Mahavir Jayanti",      "day": "Wednesday"},
        {"date": "2026-04-03", "description": "Good Friday",          "day": "Friday"},
        {"date": "2026-04-14", "description": "Dr. Ambedkar Jayanti", "day": "Tuesday"},
        {"date": "2026-05-01", "description": "Maharashtra Day",      "day": "Friday"},
        {"date": "2026-08-15", "description": "Independence Day",     "day": "Saturday"},
        {"date": "2026-10-02", "description": "Gandhi Jayanti",       "day": "Friday"},
        {"date": "2026-10-22", "description": "Diwali Laxmi Pujan",   "day": "Thursday"},
        {"date": "2026-10-23", "description": "Diwali Balipratipada", "day": "Friday"},
        {"date": "2026-11-05", "description": "Guru Nanak Jayanti",   "day": "Thursday"},
        {"date": "2026-11-25", "description": "Christmas Eve",        "day": "Friday"},
        {"date": "2026-12-25", "description": "Christmas",            "day": "Friday"},
    ]
    # fetch_nse_holidays()'s live-data path always includes a "display" key
    # (the human-readable trading date string). Add it here too so fallback
    # entries have the same shape — format_holiday_message() reads h['display']
    # unconditionally and crashes with KeyError on any entry missing it.
    for h in raw:
        h["display"] = datetime.strptime(h["date"], "%Y-%m-%d").strftime("%d-%b-%Y")
    return raw

# ─────────────────────────────────────────
# CHECK IF TODAY IS HOLIDAY
# ─────────────────────────────────────────
def is_market_holiday(holidays=None):
    today = datetime.now(IST).strftime("%Y-%m-%d")

    # Check weekend first
    weekday = datetime.now(IST).weekday()
    if weekday == 5:
        return True, "Saturday — Market Closed"
    if weekday == 6:
        return True, "Sunday — Market Closed"

    # Fetch holidays if not provided
    if holidays is None:
        holidays = fetch_nse_holidays()

    # Check if today is in holiday list
    for h in holidays:
        if h["date"] == today:
            return True, h["description"]

    return False, None

# ─────────────────────────────────────────
# FETCH NSE MARKET STATUS (live)
# ─────────────────────────────────────────
def fetch_market_status():
    try:
        init_nse_session()
        url = "https://www.nseindia.com/api/marketStatus"
        r   = NSE_SESSION.get(url, timeout=10)

        if r.status_code == 200:
            data   = r.json()
            status = data.get("marketState", [])
            result = {}
            for s in status:
                market = s.get("market", "")
                state  = s.get("marketStatus", "")
                tradedate = s.get("tradeDate", "")
                result[market] = {
                    "status":    state,
                    "tradeDate": tradedate,
                    "index":     s.get("index", ""),
                }
            print(f"  ✅ Market status fetched")
            return result
        else:
            print(f"  ❌ Market status error: {r.status_code}")
            return {}
    except Exception as e:
        print(f"  ❌ Market status failed: {e}")
        return {}

# ─────────────────────────────────────────
# FETCH NSE INDEX DATA (Nifty50, BankNifty)
# ─────────────────────────────────────────
def fetch_nse_indices():
    indices = {}
    try:
        init_nse_session()

        # Nifty 50
        url = "https://www.nseindia.com/api/allIndices"
        r   = NSE_SESSION.get(url, timeout=10)

        if r.status_code == 200:
            data = r.json()
            for item in data.get("data", []):
                name = item.get("index", "")
                if name in ["NIFTY 50", "NIFTY BANK", "NIFTY IT",
                            "NIFTY METAL", "NIFTY AUTO", "INDIA VIX"]:
                    indices[name] = {
                        "last":    item.get("last", 0),
                        "change":  item.get("change", 0),
                        "pChange": item.get("percentChange", 0),
                        "high":    item.get("high", 0),
                        "low":     item.get("low", 0),
                        "open":    item.get("open", 0),
                    }
            print(f"  ✅ NSE indices fetched: {list(indices.keys())}")
        return indices
    except Exception as e:
        print(f"  ❌ NSE indices failed: {e}")
        return {}

# ─────────────────────────────────────────
# FETCH NSE FII/DII DATA
# ─────────────────────────────────────────
def fetch_fii_dii():
    try:
        init_nse_session()
        url = "https://www.nseindia.com/api/fiidiiTradeReact"
        r   = NSE_SESSION.get(url, timeout=10)

        if r.status_code == 200:
            data   = r.json()
            result = []

            for row in data[:5]:  # last 5 days
                result.append({
                    "date":       row.get("date", ""),
                    "fii_buy":    row.get("fiiBuy", 0),
                    "fii_sell":   row.get("fiiSell", 0),
                    "fii_net":    row.get("fiiNet", 0),
                    "dii_buy":    row.get("diiBuy", 0),
                    "dii_sell":   row.get("diiSell", 0),
                    "dii_net":    row.get("diiNet", 0),
                })

            print(f"  ✅ FII/DII data fetched: {len(result)} days")
            return result
        else:
            print(f"  ❌ FII/DII error: {r.status_code}")
            return []
    except Exception as e:
        print(f"  ❌ FII/DII failed: {e}")
        return []

# ─────────────────────────────────────────
# FETCH NSE TOP GAINERS & LOSERS
# ─────────────────────────────────────────
def fetch_top_movers():
    try:
        init_nse_session()
        movers = {"gainers": [], "losers": []}

        # Top gainers Nifty50
        url = "https://www.nseindia.com/api/live-analysis-variations?index=gainers"
        r   = NSE_SESSION.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("NIFTY", {}).get("data", [])[:5]:
                movers["gainers"].append({
                    "symbol":  item.get("symbol", ""),
                    "ltp":     item.get("ltp", 0),
                    "change":  item.get("netPrice", 0),
                })

        # Top losers Nifty50
        url = "https://www.nseindia.com/api/live-analysis-variations?index=losers"
        r   = NSE_SESSION.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for item in data.get("NIFTY", {}).get("data", [])[:5]:
                movers["losers"].append({
                    "symbol":  item.get("symbol", ""),
                    "ltp":     item.get("ltp", 0),
                    "change":  item.get("netPrice", 0),
                })

        print(f"  ✅ Top movers: {len(movers['gainers'])} gainers, {len(movers['losers'])} losers")
        return movers
    except Exception as e:
        print(f"  ❌ Top movers failed: {e}")
        return {"gainers": [], "losers": []}

# ─────────────────────────────────────────
# FETCH UPCOMING HOLIDAYS (next 7 days)
# ─────────────────────────────────────────
def get_upcoming_holidays(holidays=None, days=7):
    if holidays is None:
        holidays = fetch_nse_holidays()

    today    = datetime.now(IST)
    upcoming = []

    for h in holidays:
        try:
            hdate = datetime.strptime(h["date"], "%Y-%m-%d").replace(tzinfo=IST)
            delta = (hdate - today).days
            if 0 < delta <= days:
                upcoming.append({**h, "days_away": delta})
        except Exception:
            continue

    return sorted(upcoming, key=lambda x: x["days_away"])

# ─────────────────────────────────────────
# GET FULL NSE SNAPSHOT
# ─────────────────────────────────────────
def get_nse_snapshot():
    """
    Returns complete NSE data snapshot:
    - is_holiday + reason
    - market status
    - indices
    - FII/DII
    - top movers
    - upcoming holidays
    """
    print("  Fetching NSE snapshot...")

    holidays         = fetch_nse_holidays()
    is_holiday, reason = is_market_holiday(holidays)
    upcoming         = get_upcoming_holidays(holidays)

    if is_holiday:
        return {
            "is_holiday":       True,
            "holiday_reason":   reason,
            "upcoming":         upcoming,
            "market_status":    {},
            "indices":          {},
            "fii_dii":          [],
            "movers":           {"gainers": [], "losers": []},
        }

    # Market is open — fetch all data
    market_status = fetch_market_status()
    indices       = fetch_nse_indices()
    fii_dii       = fetch_fii_dii()
    movers        = fetch_top_movers()

    return {
        "is_holiday":     False,
        "holiday_reason": None,
        "upcoming":       upcoming,
        "market_status":  market_status,
        "indices":        indices,
        "fii_dii":        fii_dii,
        "movers":         movers,
    }

# ─────────────────────────────────────────
# FORMAT FII/DII SUMMARY STRING
# ─────────────────────────────────────────
def format_fii_dii_summary(fii_dii):
    if not fii_dii:
        return "FII/DII data not available"

    latest = fii_dii[0]
    fii_net = float(latest.get("fii_net", 0))
    dii_net = float(latest.get("dii_net", 0))
    date    = latest.get("date", "")

    fii_str = f"{'SOLD' if fii_net < 0 else 'BOUGHT'} ₹{abs(fii_net):.0f} Cr"
    dii_str = f"{'SOLD' if dii_net < 0 else 'BOUGHT'} ₹{abs(dii_net):.0f} Cr"

    # 5 day trend
    fii_trend = sum(1 for d in fii_dii if float(d.get("fii_net",0)) > 0)
    dii_trend = sum(1 for d in fii_dii if float(d.get("dii_net",0)) > 0)

    return (
        f"FII: {fii_str} ({date})\n"
        f"DII: {dii_str} ({date})\n"
        f"5-day trend: FII buying {fii_trend}/5 days | DII buying {dii_trend}/5 days"
    )

# ─────────────────────────────────────────
# FORMAT INDICES SUMMARY STRING
# ─────────────────────────────────────────
def format_indices_summary(indices):
    if not indices:
        return "Index data not available"

    lines = []
    order = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY METAL", "NIFTY AUTO", "INDIA VIX"]
    emoji = {"NIFTY 50":"📊", "NIFTY BANK":"🏦", "NIFTY IT":"💻",
             "NIFTY METAL":"⚙️", "NIFTY AUTO":"🚗", "INDIA VIX":"⚡"}

    for name in order:
        if name in indices:
            d = indices[name]
            chg   = float(d.get("pChange", 0))
            arrow = "🟢" if chg > 0 else "🔴" if chg < 0 else "⚪"
            lines.append(
                f"{emoji.get(name,'📈')} {name}: "
                f"{d.get('last', 'N/A')} {arrow} {chg:+.2f}%"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    # Test run
    print("Testing NSE data fetcher...")
    snapshot = get_nse_snapshot()
    print(f"\nHoliday: {snapshot['is_holiday']} — {snapshot['holiday_reason']}")
    print(f"\nIndices:\n{format_indices_summary(snapshot['indices'])}")
    print(f"\nFII/DII:\n{format_fii_dii_summary(snapshot['fii_dii'])}")
    if snapshot['upcoming']:
        print(f"\nUpcoming holidays:")
        for h in snapshot['upcoming']:
            print(f"  {h['display']} — {h['description']} ({h['days_away']} days)")

import requests
import os
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from nse_data import get_nse_snapshot, format_indices_summary
from derivatives_data import (
    get_derivatives_snapshot,
    format_derivatives_for_prompt
)

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY",  "")
SESSION_LABEL      = os.getenv("SESSION_LABEL", "BEST_ENTRY")

IST = timezone(timedelta(hours=5, minutes=30))

# ─────────────────────────────────────────
# INSTITUTIONAL ANALYSIS PROMPT
# ─────────────────────────────────────────
INSTITUTIONAL_PROMPT = """You are a senior institutional derivatives analyst at a top Indian fund house.
You have access to real NSE data. Analyze it like a prop desk trader — not a retail advisor.

Today: {today} | Time: {time_now} IST | Session: {session}

═══════════════════════════════════
DERIVATIVES & INSTITUTIONAL DATA
═══════════════════════════════════
{derivatives_data}

═══════════════════════════════════
NSE LIVE INDEX DATA
═══════════════════════════════════
{indices_data}

═══════════════════════════════════
LATEST MARKET NEWS
═══════════════════════════════════
{news}

═══════════════════════════════════

Provide institutional-level analysis in EXACTLY this format (plain text, no markdown):

MARKET SENTIMENT: [BULLISH/BEARISH/SIDEWAYS] | STRENGTH: [WEAK/MODERATE/STRONG]
VERDICT: [TRADE/AVOID/WAIT] | CONFIDENCE: [0-100]%

━━ SENTIMENT REASONING ━━
[2-3 lines — data-driven, cite specific numbers from above]

━━ VIX ANALYSIS ━━
Current: [value and what it means for options pricing today]
Strategy implication: [buy/sell options or spreads?]

━━ OPTION CHAIN INSIGHT ━━
Nifty:
  Resistance (Call wall): [strike] — [OI in lakhs] lakh OI
  Support (Put wall): [strike] — [OI in lakhs] lakh OI
  PCR: [value] — [interpretation]
  Max Pain: [level] — [implication for expiry]
  Expected range today: [low] — [high]

BankNifty:
  Resistance: [strike] | Support: [strike]
  PCR: [value] | Max Pain: [level]

━━ FUTURES ANALYSIS ━━
Nifty Futures: [Long buildup/Short buildup/Short covering/Long unwinding]
BankNifty Futures: [same]
Smart money direction: [what institutions are likely doing]

━━ FII/DII INSTITUTIONAL POSITIONING ━━
FII cash: [net amount and trend]
FII F&O: [index futures and options positioning]
DII counter: [what DIIs doing]
Interpretation: [what smart money is doing overall]

━━ HIGH PROBABILITY F&O TRADES ━━

TRADE 1 — NIFTY
  Direction: [CALL/PUT]
  Strike: [price]
  Expiry: [date]
  Entry range: [price1]–[price2]
  Stop loss: [price]
  Target 1: [price] | Target 2: [price]
  Risk:Reward: [ratio]
  Probability: [%]
  Reasoning: [one line — cite OI/PCR/futures data]

TRADE 2 — BANKNIFTY
  Direction: [CALL/PUT]
  Strike: [price]
  Expiry: [date]
  Entry range: [price1]–[price2]
  Stop loss: [price]
  Target 1: [price] | Target 2: [price]
  Risk:Reward: [ratio]
  Probability: [%]
  Reasoning: [one line]

TRADE 3 — STOCK F&O (if strong signal exists)
  Stock: [name]
  Direction: [CALL/PUT/FUTURES]
  Entry: [price] | SL: [price] | Target: [price]
  Probability: [%]
  Reasoning: [one line]

━━ SECTORAL VIEW ━━
Strong: [sectors with reasoning]
Weak: [sectors with reasoning]

━━ RISK MANAGEMENT ━━
Ideal R:R for today: [ratio]
Max capital per trade: [% of trading capital]
Key risk: [single biggest risk today]

━━ REALITY GAUGE ━━
Bull invalidation: [specific level/event that kills bullish view]
Bear invalidation: [specific level/event that kills bearish view]
Trend reversal signal: [what to watch]
Wild card: [unexpected event that could move market 2%+]

━━ KEY LEVELS SUMMARY ━━
Nifty: Support [s1]/[s2] | Resistance [r1]/[r2]
BankNifty: Support [s1]/[s2] | Resistance [r1]/[r2]

Keep total under 600 words. Be brutally honest. If data is insufficient to trade, say AVOID."""

# ─────────────────────────────────────────
# NEWS FETCHER
# ─────────────────────────────────────────
def fetch_headlines():
    feeds = [
        "https://news.google.com/rss/search?q=NSE+Nifty+Sensex+India+stock+market+today&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=FII+India+derivatives+futures+options&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=crude+oil+RBI+India+rupee+global+market&hl=en-IN&gl=IN&ceid=IN:en",
    ]
    all_h = []
    for url in feeds:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:7]:
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
    return unique[:15]

# ─────────────────────────────────────────
# CLAUDE INSTITUTIONAL ANALYSIS
# ─────────────────────────────────────────
def get_institutional_analysis(derivatives_snap, nse_snap, headlines, session):
    if not ANTHROPIC_API_KEY:
        return None

    today    = datetime.now(IST).strftime("%d %b %Y %A")
    time_now = datetime.now(IST).strftime("%I:%M %p")
    deriv_str  = format_derivatives_for_prompt(derivatives_snap)
    indices_str = format_indices_summary(nse_snap.get("indices", {}))
    news_str   = "\n".join([f"- {h}" for h in headlines[:12]])

    prompt = INSTITUTIONAL_PROMPT.format(
        today=today,
        time_now=time_now,
        session=session,
        derivatives_data=deriv_str,
        indices_data=indices_str,
        news=news_str,
    )

    try:
        print("  Calling Claude for institutional analysis...")
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 1500,
                "messages":   [{"role": "user", "content": prompt}],
            },
            timeout=40
        )
        if res.status_code == 200:
            print("  ✅ Institutional analysis done")
            return res.json()["content"][0]["text"]
        print(f"  ❌ Claude error: {res.status_code}")
        return None
    except Exception as e:
        print(f"  ❌ Claude failed: {e}")
        return None

# ─────────────────────────────────────────
# FORMAT TELEGRAM MESSAGE
# ─────────────────────────────────────────
def format_message(session, nse_snap, derivatives_snap, analysis):
    now = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    vix = derivatives_snap.get("vix", {})
    no  = derivatives_snap.get("nifty_options", {})
    bno = derivatives_snap.get("banknifty_options", {})

    lines = [
        "🏦 *VIRALVIBE — INSTITUTIONAL ANALYSIS*",
        f"📅 {now}  |  Session: {session.replace('_',' ')}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    # Quick snapshot
    indices_str = format_indices_summary(nse_snap.get("indices", {}))
    if indices_str:
        lines += ["\n📈 *LIVE MARKET*", indices_str]

    # Key derivatives snapshot
    lines.append("\n📊 *DERIVATIVES SNAPSHOT*")
    if vix:
        vix_val = vix.get("vix", 0)
        vix_chg = vix.get("chg_pct", 0)
        vix_icon = "🔴" if vix_val > 20 else "🟡" if vix_val > 15 else "🟢"
        lines.append(f"{vix_icon} VIX: {vix_val} ({vix_chg:+.2f}%) — {vix.get('signal','')}")

    if no:
        lines.append(f"📊 Nifty PCR: {no.get('pcr')} | MaxPain: {no.get('max_pain')} | Range: {no.get('max_put_strike')}–{no.get('max_call_strike')}")

    if bno:
        lines.append(f"🏦 BankNifty PCR: {bno.get('pcr')} | MaxPain: {bno.get('max_pain')} | Range: {bno.get('max_put_strike')}–{bno.get('max_call_strike')}")

    # Futures signals
    nf = derivatives_snap.get("nifty_futures", {})
    bf = derivatives_snap.get("banknifty_futures", {})
    if nf.get("contracts"):
        lines.append(f"📈 Nifty Fut: {nf['contracts'][0].get('buildup','N/A')}")
    if bf.get("contracts"):
        lines.append(f"🏦 BNF Fut: {bf['contracts'][0].get('buildup','N/A')}")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Full AI analysis
    if analysis:
        lines += ["\n🤖 *INSTITUTIONAL AI ANALYSIS*\n", analysis]
    else:
        lines.append("\n⚠️ AI analysis unavailable — check API key")

    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        "⚠️ _F&O trading involves high risk. Education only._",
        "⚠️ _Not SEBI registered advice. Use strict stop loss._",
        "🏦 _ViralVibe Institutional Bot_",
    ]
    return "\n".join(lines)

def format_holiday_message(reason, upcoming):
    now = datetime.now(IST).strftime("%d %b %Y | %I:%M %p IST")
    lines = [
        "🏦 *VIRALVIBE INSTITUTIONAL BOT*",
        f"📅 {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"\n🏖 *Market Holiday: {reason}*",
        "NSE & BSE closed. F&O market closed.",
    ]
    if upcoming:
        lines.append("\n📅 *Next trading days:*")
        for h in upcoming[:3]:
            lines.append(f"  • {h['display']} — {h['description']}")
    lines += [
        "\n💡 Use today to study option chain concepts",
        "🤖 _ViralVibe Institutional Bot_"
    ]
    return "\n".join(lines)

# ─────────────────────────────────────────
# SEND TELEGRAM
# ─────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ No credentials\n")
        print(message[:800])
        return
    for part in [message[i:i+4000] for i in range(0, len(message), 4000)]:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "Markdown"},
                timeout=15
            )
            print("  ✅ Sent!" if r.status_code == 200 else f"  ❌ {r.status_code}")
        except Exception as e:
            print(f"  ❌ {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run():
    print(f"\n{'='*55}")
    print(f"INSTITUTIONAL ANALYSIS | {SESSION_LABEL}")
    print(f"TIME: {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")
    print("="*55)

    # 1. Holiday check
    print("\n[1] Checking NSE market status...")
    nse_snap = get_nse_snapshot()

    if nse_snap["is_holiday"]:
        reason   = nse_snap["holiday_reason"]
        upcoming = nse_snap["upcoming"]
        print(f"  🏖 Holiday: {reason}")
        if SESSION_LABEL in ["MORNING_BRIEFING", "BEST_ENTRY"]:
            send_telegram(format_holiday_message(reason, upcoming))
        return

    print("  ✅ Market open")

    # 2. Fetch derivatives data
    print("\n[2] Fetching derivatives data (options + futures + FII F&O)...")
    derivatives_snap = get_derivatives_snapshot()

    # 3. Fetch news
    print("\n[3] Fetching news headlines...")
    headlines = fetch_headlines()

    # 4. Get institutional AI analysis
    print("\n[4] Running institutional AI analysis...")
    analysis = get_institutional_analysis(
        derivatives_snap, nse_snap, headlines, SESSION_LABEL
    )

    # 5. Format and send
    print("\n[5] Sending to Telegram...")
    msg = format_message(SESSION_LABEL, nse_snap, derivatives_snap, analysis)
    send_telegram(msg)

    print("\n✅ Done!")

if __name__ == "__main__":
    run()

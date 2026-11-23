#!/usr/bin/env python3
# ================================================================
# AI CRYPTO NEWS & MACRO INTELLIGENCE BY SALI
# Teljes kriptopiac + kiemelt BTC | Magyar Telegram-riasztások
#
# FONTOS:
# - A hírek és makroadatok észlelési ideje a forrás közzétételétől,
#   a feed/API frissítésétől és a POLL_SECONDS beállítástól függ.
# - Garantált, szó szerinti "abban a milliszekundumban" kézbesítés
#   külső RSS/API forrásokból nem lehetséges. Ez a bot folyamatosan
#   ellenőriz, és az észlelt új elemet azonnal továbbítja Telegramra.
# ================================================================

import os
import re
import json
import time
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
import feedparser
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "AI PRO BY SALI"
POLL_SECONDS = max(10, int(os.getenv("POLL_SECONDS", "20")))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))
STATE_FILE = Path(os.getenv("STATE_FILE", "sali_alert_state.json"))
MAX_SUMMARY_CHARS = 3500

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "").strip()

# Sűrűn frissülő, nyilvános RSS-források. A feedek elérhetősége
# és frissítési gyakorisága a kiadóktól függ.
NEWS_FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Bitcoin Magazine": "https://bitcoinmagazine.com/.rss/full/",
    "Blockworks": "https://blockworks.co/feed",
    "Decrypt": "https://decrypt.co/feed",
    "The Block": "https://www.theblock.co/rss.xml",
}

# Elsődleges makro- és szabályozói közlemények RSS-forrásai.
MACRO_FEEDS = {
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "BLS": "https://www.bls.gov/feed/news_release.rss",
    "BEA": "https://www.bea.gov/news/blog/rss.xml",
    "U.S. Treasury": "https://home.treasury.gov/news/press-releases/feed",
    "SEC": "https://www.sec.gov/news/pressreleases.rss",
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "SaliCryptoAlertBot/1.0 (personal news monitoring)"
})

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger(APP_NAME)

def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Az állapotfájl nem olvasható: %s", exc)
    return {"seen": [], "feed_etags": {}, "feed_modified": {}}

STATE = load_state()
SEEN = set(STATE.get("seen", []))
MAX_SEEN = 6000

def save_state():
    STATE["seen"] = list(SEEN)[-MAX_SEEN:]
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)

def clean_html(value):
    value = re.sub(r"<(script|style).*?</\\1>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"&nbsp;|&#160;", " ", value)
    value = re.sub(r"&amp;", "&", value)
    value = re.sub(r"&quot;", '"', value)
    value = re.sub(r"&#39;|&apos;", "'", value)
    return re.sub(r"\\s+", " ", value).strip()

def entry_time(entry):
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()

def make_id(source, entry):
    raw = "|".join([
        source,
        str(entry.get("id") or entry.get("guid") or entry.get("link") or ""),
        str(entry.get("title") or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()

def telegram_send(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("Hiányzik a TELEGRAM_BOT_TOKEN vagy TELEGRAM_CHAT_ID a .env fájlból.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        response = SESSION.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message[:4000],
            "disable_web_page_preview": True,
        }, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(str(data))
        return True
    except Exception as exc:
        log.exception("Telegram-küldési hiba: %s", exc)
        return False

def groq_analyze(title, summary, source, category, macro_data=None):
    """Magyar nyelvű, strukturált besorolás. Sikertelenségkor biztonságos semleges fallback."""
    if not GROQ_API_KEY:
        return {
            "rating": "SEMLEGES",
            "impact": "NEM ÉRTÉKELHETŐ",
            "score": 0,
            "btc": "SEMLEGES",
            "market": "SEMLEGES",
            "horizon": "NEM MEGHATÁROZHATÓ",
            "reason": "Nincs beállítva GROQ_API_KEY; az AI-értékelés nem futott le.",
            "confidence": 0,
        }

    extra = ""
    if macro_data:
        extra = "\nMakroadatok (ha rendelkezésre állnak): " + json.dumps(
            macro_data, ensure_ascii=False
        )

    system_prompt = """
Te egy óvatos, tényszerű kriptopiaci hír- és makroelemző vagy.
KIZÁRÓLAG magyarul válaszolj, pontosan az alábbi JSON-kulcsokkal:
rating, impact, score, btc, market, horizon, reason, confidence.
rating és btc és market csak ezek egyike lehet:
ERŐSEN BIKÁS, BIKÁS, SEMLEGES, MEDVÉS, ERŐSEN MEDVÉS.
impact: ALACSONY, KÖZEPES, MAGAS vagy KRITIKUS.
score: egész szám 1-100 között, a hír jelentősége, nem árfolyamcél.
confidence: egész szám 0-100 között.
horizon: RÖVID TÁV, KÖZÉPTÁV, HOSSZÚ TÁV vagy VEGYES.
A reason legfeljebb 3 tömör magyar mondat.
Ne találj ki tényeket. A hír irányát a kriptóra gyakorolt várható hatás
alapján értékeld, ne pusztán a cím hangulata szerint.
Vedd figyelembe, hogy a már beárazott vagy vártnál kevésbé rossz adat
akár pozitív piaci reakciót is kiválthat. Ha nincs elég információ,
válaszd a SEMLEGES besorolást és alacsony confidence értéket.
Ne állítsd, hogy az árfolyam biztosan az adott irányba megy.
Csak érvényes JSON-t adj vissza, markdown nélkül.
"""
    user_prompt = (
        f"Kategória: {category}\nForrás: {source}\nCím: {title}\n"
        f"Leírás: {summary[:MAX_SUMMARY_CHARS]}{extra}\n"
        "Értékeld a Bitcoinra és a teljes kriptopiacra gyakorolt várható hatást."
    )
    try:
        response = SESSION.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=25,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        result = json.loads(content)
        allowed = {"ERŐSEN BIKÁS", "BIKÁS", "SEMLEGES", "MEDVÉS", "ERŐSEN MEDVÉS"}
        for key in ("rating", "btc", "market"):
            if result.get(key) not in allowed:
                result[key] = "SEMLEGES"
        result["score"] = max(1, min(100, int(result.get("score", 1))))
        result["confidence"] = max(0, min(100, int(result.get("confidence", 0))))
        return result
    except Exception as exc:
        log.exception("Groq-elemzési hiba: %s", exc)
        return {
            "rating": "SEMLEGES", "impact": "NEM ÉRTÉKELHETŐ",
            "score": 0, "btc": "SEMLEGES", "market": "SEMLEGES",
            "horizon": "NEM MEGHATÁROZHATÓ",
            "reason": "Az AI-elemzés technikai hiba miatt nem készült el.",
            "confidence": 0,
        }

def emoji_for(rating):
    return {
        "ERŐSEN BIKÁS": "🟢🚀",
        "BIKÁS": "🟢",
        "SEMLEGES": "⚪",
        "MEDVÉS": "🔴",
        "ERŐSEN MEDVÉS": "🔴🧨",
    }.get(rating, "⚪")

def format_alert(category, source, title, summary, link, published, analysis, macro_data=None):
    lines = [
        "🚨 AI PRO BY SALI – ÚJ PIACI RIASZTÁS",
        "",
        f"📌 TÍPUS: {category}",
        f"📰 FORRÁS: {source}",
        f"🗞 HÍR: {title}",
        "",
        f"{emoji_for(analysis['rating'])} MINŐSÍTÉS: {analysis['rating']}",
        f"💥 HÍR JELENTŐSÉGE: {analysis['score']}/100",
        f"⚠️ VÁRHATÓ HATÁS: {analysis['impact']}",
        f"₿ BITCOIN: {analysis['btc']}",
        f"🌐 TELJES KRIPTOPIAC: {analysis['market']}",
        f"⏳ IDŐTÁV: {analysis['horizon']}",
        f"🎯 AI BIZALMI SZINT: {analysis['confidence']}%",
        "",
        f"🧠 MAGYARÁZAT: {analysis['reason']}",
    ]
    if macro_data:
        lines += [
            "",
            "📊 MAKRÓADATOK:",
            f"• Tény: {macro_data.get('actual', 'nincs adat')}",
            f"• Várakozás: {macro_data.get('estimate', 'nincs adat')}",
            f"• Előző: {macro_data.get('prev', 'nincs adat')}",
        ]
    lines += [
        "",
        f"🕒 ÉSZLELÉS (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        f"🗓 KÖZZÉTÉTEL: {published}",
        f"🔗 EREDETI FORRÁS: {link or 'nincs hivatkozás'}",
        "",
        "Megjegyzés: ez AI-alapú hírértelmezés, nem garantált árfolyam-előrejelzés.",
    ]
    return "\n".join(lines)

def process_entry(source, entry, category, macro_data=None):
    uid = make_id(source, entry)
    if uid in SEEN:
        return
    title = clean_html(entry.get("title", "")) or "(Cím nélkül)"
    summary = clean_html(entry.get("summary", "") or entry.get("description", ""))
    link = entry.get("link", "")
    published = entry_time(entry)
    log.info("Új elem: [%s] %s", source, title)

    analysis = groq_analyze(title, summary, source, category, macro_data)
    message = format_alert(
        category, source, title, summary, link, published, analysis, macro_data
    )
    if telegram_send(message):
        SEEN.add(uid)
        save_state()
        log.info("Telegram-riasztás elküldve: %s", title)
    else:
        log.error("A riasztás küldése nem sikerült; később újrapróbáljuk.")

def fetch_feed(source, url, category):
    headers = {}
    etag = STATE.get("feed_etags", {}).get(url)
    modified = STATE.get("feed_modified", {}).get(url)
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified

    try:
        response = SESSION.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 304:
            return
        response.raise_for_status()
        if response.headers.get("ETag"):
            STATE.setdefault("feed_etags", {})[url] = response.headers["ETag"]
        if response.headers.get("Last-Modified"):
            STATE.setdefault("feed_modified", {})[url] = response.headers["Last-Modified"]
        parsed = feedparser.parse(response.content)
        # A feed régi elemei első induláskor ne generáljanak több száz riasztást.
        entries = parsed.entries
        if not STATE.get("initialized"):
            entries = entries[:2]
        for entry in reversed(entries):
            process_entry(source, entry, category)
        save_state()
    except Exception as exc:
        log.warning("Feed-hiba (%s): %s", source, exc)

def fetch_finnhub_calendar():
    """A makronaptár tényadatának megjelenését figyeli; csak actual értékkel riaszt."""
    if not FINNHUB_API_KEY:
        return
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=1)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    url = "https://finnhub.io/api/v1/calendar/economic"
    try:
        response = SESSION.get(
            url,
            params={"from": start, "to": end, "token": FINNHUB_API_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        events = response.json().get("economicCalendar", [])
        for event in events:
            actual = event.get("actual")
            # A null/üres actual még nem publikált tényadat.
            if actual is None or str(actual).strip() == "":
                continue
            country = str(event.get("country", ""))
            # Elsődleges fókusz: USA, de a nagyobb globális eseményeket is figyeljük.
            if country not in ("US", "USA", "United States"):
                continue
            name = str(event.get("event", "Makrogazdasági adat"))
            event_time = str(event.get("time", ""))
            uid_raw = f"FINNHUB|{event_time}|{name}|{actual}"
            uid = hashlib.sha256(uid_raw.encode()).hexdigest()
            if uid in SEEN:
                continue
            data = {
                "actual": actual,
                "estimate": event.get("estimate"),
                "prev": event.get("prev"),
                "unit": event.get("unit"),
                "country": country,
            }
            synthetic_entry = {
                "id": uid_raw,
                "title": f"🇺🇸 {name} – megjelent a tényadat",
                "summary": (
                    f"Tényadat: {actual}; várakozás: {event.get('estimate')}; "
                    f"előző: {event.get('prev')}; időpont: {event_time}."
                ),
                "link": "https://finnhub.io/docs/api/economic-calendar",
                "published": event_time,
            }
            process_macro(uid, synthetic_entry, data)
    except Exception as exc:
        log.warning("Finnhub makronaptár-hiba: %s", exc)

def process_macro(uid, entry, data):
    if uid in SEEN:
        return
    title = clean_html(entry.get("title", ""))
    summary = clean_html(entry.get("summary", ""))
    analysis = groq_analyze(
        title, summary, "Finnhub gazdasági naptár", "MAKROADAT", data
    )
    message = format_alert(
        "FRISS MAKROADAT", "Finnhub gazdasági naptár", title, summary,
        entry.get("link", ""), entry.get("published", ""), analysis, data
    )
    if telegram_send(message):
        SEEN.add(uid)
        save_state()

def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise SystemExit(
            "Állítsd be a TELEGRAM_BOT_TOKEN és TELEGRAM_CHAT_ID értékeket a .env fájlban."
        )
    log.info("%s elindult. Ellenőrzési időköz: %s mp", APP_NAME, POLL_SECONDS)
    telegram_send(
        "🟢 AI PRO BY SALI – A hír- és makrofigyelő elindult.\n"
        f"Figyelési ciklus: {POLL_SECONDS} másodperc.\n"
        "Nyelv: magyar | Piac: teljes kriptopiac + kiemelt BTC."
    )
    while True:
        for source, url in NEWS_FEEDS.items():
            fetch_feed(source, url, "KRIPTÓHÍR")
        for source, url in MACRO_FEEDS.items():
            fetch_feed(source, url, "MAKRÓ / SZABÁLYOZÓI HÍR")
        fetch_finnhub_calendar()
        STATE["initialized"] = True
        save_state()
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()

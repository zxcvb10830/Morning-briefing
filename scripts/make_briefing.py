"""Generate morning-briefing.mp3 (Traditional Chinese, Taiwan) from Yahoo Finance + RSS."""
import asyncio, datetime as dt, email.utils, sys
import requests, feedparser, edge_tts

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
ITEMS = [("TSLA", "特斯拉"), ("^GSPC", "標普五百指數"), ("^DJI", "道瓊指數"), ("SMCI", "美超微"), ("HIMS", "Hims and Hers")]
NEWS_TICKERS = ["TSLA", "SMCI", "HIMS"]
TSLA_SHARES, TSLA_COST = 300, 360.0
WORLD_FEEDS = ["https://feeds.bbci.co.uk/news/world/rss.xml", "https://feeds.npr.org/1001/rss.xml"]

def quote(sym):
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=10d&interval=1d", headers=UA, timeout=20)
        res = r.json()["chart"]["result"][0]
        ts, cl = res["timestamp"], res["indicators"]["quote"][0]["close"]
        bars = [(t, c) for t, c in zip(ts, cl) if c is not None]
        # drop today's in-progress bar if market currently open
        meta = res["meta"]; per = meta.get("currentTradingPeriod", {}).get("regular", {})
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        if per and per.get("start", 0) <= now < per.get("end", 0) and bars and bars[-1][0] >= per["start"] - 3600:
            bars = bars[:-1]
        (t1, c1), (_, c0) = bars[-1], bars[-2]
        day = dt.datetime.fromtimestamp(t1 + meta.get("gmtoffset", -18000), dt.timezone.utc).date()
        return day, c1, (c1 / c0 - 1) * 100
    except Exception as e:
        print("quote fail", sym, e, file=sys.stderr); return None

_tr = None
def zh(text):
    global _tr
    try:
        if _tr is None:
            from deep_translator import GoogleTranslator
            _tr = GoogleTranslator(source="en", target="zh-TW")
        out = _tr.translate(text)
        return out.strip().rstrip("。.") if out else None
    except Exception as e:
        print("translate fail", e, file=sys.stderr); return None

def entry_date(e):
    try: return email.utils.parsedate_to_datetime(e.published).astimezone(dt.timezone(dt.timedelta(hours=-5))).date()
    except Exception: return None

def ticker_news(sym, day):
    try:
        f = feedparser.parse(requests.get(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US", headers=UA, timeout=20).content)
        hits = [e.title for e in f.entries if entry_date(e) in (day, day + dt.timedelta(days=1))]
        return hits[:1]
    except Exception as e:
        print("news fail", sym, e, file=sys.stderr); return []

def world_news():
    for u in WORLD_FEEDS:
        try:
            f = feedparser.parse(requests.get(u, headers=UA, timeout=20).content)
            if f.entries: return f.entries[0].title
        except Exception: pass
    return None

def updown(p): return f"上漲百分之{abs(p):.1f}" if p >= 0 else f"下跌百分之{abs(p):.1f}"

def build():
    q = {s: quote(s) for s, _ in ITEMS}
    day = next((v[0] for v in q.values() if v), None)
    if day is None: sys.exit("no market data")
    lines = [f"早安！這是你的晨間簡報，整理美股 {day.month} 月 {day.day} 日的收盤。"]
    v = q["TSLA"]
    if v:
        pl = (v[1] - TSLA_COST) * TSLA_SHARES
        lines.append(f"先看特斯拉，收在 {v[1]:.2f} 美元，{updown(v[2])}。以你三百股、均價三百六來算，目前{'帳面賺' if pl>=0 else '帳面虧'}大約 {abs(pl):,.0f} 美元。")
    for h in ticker_news("TSLA", day):
        t = zh(h); lines.append(f"特斯拉的新聞：{t}。" if t else "特斯拉昨天也有一些新聞值得留意。")
    g, d = q["^GSPC"], q["^DJI"]
    if g or d:
        s = "大盤方面，"
        if g: s += f"標普五百收在 {g[1]:,.0f} 點，{updown(g[2])}"
        if d: s += f"{'；' if g else ''}道瓊收在 {d[1]:,.0f} 點，{updown(d[2])}"
        lines.append(s + "。")
    for sym, name in [("SMCI", "美超微"), ("HIMS", "Hims and Hers")]:
        v = q[sym]
        if v: lines.append(f"{name}收在 {v[1]:.2f} 美元，{updown(v[2])}。")
        for h in ticker_news(sym, day):
            t = zh(h)
            if t: lines.append(f"相關新聞：{t}。")
    w = world_news()
    if w:
        t = zh(w)
        if t: lines.append(f"最後看一則國際焦點：{t}。")
    lines.append("美股今晚台灣時間十點半開盤。以上是資訊整理，不是投資建議。")
    return "\n".join(lines)

async def main():
    text = build(); print(text)
    await edge_tts.Communicate(text, "zh-TW-HsiaoChenNeural", rate="+8%").save("morning-briefing.mp3")

if __name__ == "__main__":
    asyncio.run(main())

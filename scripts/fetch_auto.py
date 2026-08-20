#!/usr/bin/env python3
"""每日自動抓取未來事件 → 合併進 data/events.json
來源：
  1. 規則事件（台股營收截止、台指期結算、美國非農預定日）滾動生成未來 4 個月
  2. 台股法說會（證交所「每日重大訊息」中之法人說明會公告；只納入 watchlist 公司）
  3. 金十數據 MCP 財經日曆（star>=3 的未來事件）
原則：只新增/更新 source 為 auto:* 的事件；絕不動 manual / ai / seed 事件。
所有錯誤僅記錄不中斷。log 寫入 logs/fetch_log.txt（會被 commit，方便遠端檢查）。
"""
import json, os, re, sys, hashlib, urllib.request, urllib.error
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "data", "events.json")
WL = os.path.join(ROOT, "data", "watchlist.json")
LOGF = os.path.join(ROOT, "logs", "fetch_log.txt")
TODAY = dt.date.today()
LOG = [f"=== fetch_auto {dt.datetime.now().isoformat(timespec='seconds')} (UTC) ==="]

def log(m):
    LOG.append(str(m)); print(m, flush=True)

def http_raw(url, headers=None, data=None, timeout=40, method=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (compatible; fe-bot)"},
                                 data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), dict(r.headers)

def decode_any(b):
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try: return b.decode(enc)
        except Exception: pass
    return b.decode("utf-8", "ignore")

def iso(d): return d.strftime("%Y-%m-%d")

# ---------- 1. 規則事件 ----------
def rule_events():
    evs = []
    d = TODAY.replace(day=1)
    months = []
    for _ in range(5):
        months.append(d)
        d = (d + dt.timedelta(days=32)).replace(day=1)
    for m in months:
        dl = m.replace(day=10)
        while dl.weekday() >= 5:
            dl += dt.timedelta(days=1)
        prev = (m - dt.timedelta(days=1))
        if dl >= TODAY:
            evs.append(dict(id=f"rule-twrev-{m:%Y-%m}", date=iso(dl), precision="day",
                title=f"台股 {prev.month} 月營收公告截止", category="營收", market="台灣",
                importance=2, time="", note="上市櫃須於每月 10 日前公告（遇假日順延；此為規則推算）",
                url="", source="auto:rule", tentative=False))
        wed1 = m + dt.timedelta(days=(2 - m.weekday()) % 7)
        wed3 = wed1 + dt.timedelta(days=14)
        if wed3 >= TODAY:
            evs.append(dict(id=f"rule-taifex-{m:%Y-%m}", date=iso(wed3), precision="day",
                title="台指期／選擇權結算日", category="其他", market="台灣",
                importance=1, time="", note="每月第三個週三", url="", source="auto:rule", tentative=False))
        fri1 = m + dt.timedelta(days=(4 - m.weekday()) % 7)
        if fri1 >= TODAY:
            tw_time = "21:30" if m.month in (11, 12, 1, 2) else "20:30"
            prev_us = (m - dt.timedelta(days=1))
            evs.append(dict(id=f"rule-nfp-{m:%Y-%m}", date=iso(fri1), precision="day",
                title=f"美國 {prev_us.month} 月非農就業報告", category="總經數據", market="美國",
                importance=3, time=tw_time, note="預定日期（每月首個週五），以 BLS 公告為準",
                url="", source="auto:rule", tentative=False))
    log(f"[rule] generated {len(evs)}")
    return evs

# ---------- 2. 台股法說會（重大訊息） ----------
DATE_PATS = [
    re.compile(r"(\d{3})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(\d{3})/(\d{1,2})/(\d{1,2})"),
    re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(20\d{2})/(\d{1,2})/(\d{1,2})"),
]
def extract_date(text):
    for pat in DATE_PATS:
        m = pat.search(text or "")
        if m:
            y = int(m.group(1))
            if y < 1000: y += 1911
            try: return dt.date(y, int(m.group(2)), int(m.group(3)))
            except ValueError: continue
    return None

def tw_calls(watch):
    evs = []
    sources = [
        ("上市", "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"),
        ("上櫃", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"),
    ]
    for label, url in sources:
        try:
            raw, _ = http_raw(url, headers={"accept": "application/json", "User-Agent": "Mozilla/5.0"})
            items = json.loads(decode_any(raw))
            n = seen = 0
            for it in items:
                code = str(it.get("公司代號", "") or it.get("SecuritiesCompanyCode", "")).strip()
                subj = ""
                for k, v in it.items():
                    if "主旨" in k: subj = str(v); break
                if "法人說明會" not in subj and "法說會" not in subj: continue
                seen += 1
                if code not in watch: continue
                d = extract_date(subj)
                if not d or d < TODAY: continue
                name = str(it.get("公司名稱", "") or code).strip()
                evs.append(dict(id=f"twcall-{code}-{d:%Y%m%d}", date=iso(d), precision="day",
                    title=f"{name}（{code}）法說會", category="台股法說", market="台灣",
                    importance=3 if code == "2330" else 2, time="",
                    note=f"來源：{label}重大訊息公告", url="", source="auto:twse", tentative=False))
                n += 1
            log(f"[law-call {label}] 全部法說會公告 {seen} 筆，追蹤清單命中 {n}")
        except Exception as e:
            log(f"[law-call {label}] FAIL {type(e).__name__}: {e}")
    return evs

# ---------- 3. 金十 MCP 財經日曆 ----------
def jin10_events():
    key = os.environ.get("JIN10_KEY", "").strip()
    if not key:
        log("[jin10] no key, skip"); return []
    url = "https://mcp.jin10.com/mcp"
    session = {}
    def rpc(payload):
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream",
             "Authorization": f"Bearer {key}"}
        if session.get("id"): h["Mcp-Session-Id"] = session["id"]
        raw, rh = http_raw(url, headers=h, data=json.dumps(payload).encode(), method="POST")
        for k, v in rh.items():
            if k.lower() == "mcp-session-id": session["id"] = v
        text = decode_any(raw).strip()
        if not text: return None
        if "data:" in text:
            chunks = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")]
            for c in reversed(chunks):
                try: return json.loads(c)
                except Exception: continue
            return None
        return json.loads(text)

    def call_calendar(args):
        res = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                   "params": {"name": "list_calendar", "arguments": args}})
        content = (res or {}).get("result", {}).get("content", [])
        text = "".join(c.get("text", "") for c in content if isinstance(c, dict))
        try: return json.loads(text)
        except Exception: return None

    try:
        rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "future-events", "version": "1.0"}}})
        try: rpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except Exception: pass
        tl = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = (tl or {}).get("result", {}).get("tools", [])
        cal = next((t for t in tools if t.get("name") == "list_calendar"), None)
        if not cal:
            log(f"[jin10] no list_calendar; tools={[t.get('name') for t in tools]}"); return []
        log(f"[jin10] list_calendar inputSchema: {json.dumps(cal.get('inputSchema', {}), ensure_ascii=False)[:400]}")

        raw_items = []
        # 預設呼叫 + 嘗試帶日期參數抓未來幾天（參數不被接受就略過）
        attempts = [{}]
        for off in (1, 2, 3, 5, 7):
            attempts.append({"date": iso(TODAY + dt.timedelta(days=off))})
        for args in attempts:
            data = call_calendar(args)
            if data is None: continue
            if isinstance(data, dict):
                inner = data.get("data", data)
                if isinstance(inner, dict): inner = inner.get("items", [])
            else:
                inner = data
            if isinstance(inner, list) and inner:
                raw_items.extend(inner)
        log(f"[jin10] raw items: {len(raw_items)}")

        evs, seen = [], set()
        for it in raw_items:
            try:
                if not isinstance(it, dict): continue
                tstr = str(it.get("pub_time") or it.get("time") or it.get("date") or "")
                m = re.search(r"(\d{4})-(\d{2})-(\d{2})", tstr)
                if not m: continue
                d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                if d < TODAY or d > TODAY + dt.timedelta(days=45): continue
                star = it.get("star") or it.get("importance") or 0
                try: star = int(star)
                except Exception: star = 0
                if star < 3: continue
                title = str(it.get("title") or it.get("name") or "").strip()
                if not title or (title, iso(d)) in seen: continue
                seen.add((title, iso(d)))
                hh = re.search(r"(\d{2}:\d{2})", tstr)
                mkt = "美國" if "美" in title else "中國" if ("中国" in title or "中國" in title) else \
                      "日本" if "日本" in title else "歐洲" if ("欧" in title or "德国" in title or "法国" in title or "英国" in title) else "全球"
                eid = "jin10-" + hashlib.md5((title + iso(d)).encode()).hexdigest()[:10]
                evs.append(dict(id=eid, date=iso(d), precision="day", title=title[:60],
                    category="總經數據", market=mkt, importance=3,
                    time=(hh.group(1) if hh else ""), note=f"金十財經日曆（重要度★{star}）",
                    url="", source="auto:jin10", tentative=False))
            except Exception:
                continue
        log(f"[jin10] parsed {len(evs)}")
        return evs
    except Exception as e:
        log(f"[jin10] FAIL {type(e).__name__}: {e}")
        return []

# ---------- 合併 ----------
def norm_title(s):
    return re.sub(r"[\s（）()／/]", "", str(s or ""))[:12]

def main():
    with open(EV, encoding="utf-8") as f:
        payload = json.load(f)
    events = payload["events"]
    by_id = {e["id"]: e for e in events}
    existing_keys = {(e.get("date"), norm_title(e.get("title"))) for e in events}

    watch = set()
    try:
        with open(WL, encoding="utf-8") as f:
            watch = set(json.load(f).get("codes", []))
    except Exception as e:
        log(f"[watchlist] FAIL {e}")

    new = rule_events() + tw_calls(watch) + jin10_events()
    added = updated = 0
    for ev in new:
        ev["added_at"] = iso(TODAY)
        old = by_id.get(ev["id"])
        if old:
            if old.get("source", "").startswith("auto"):
                changed = any(old.get(k) != ev.get(k) for k in ("date", "time", "note", "title"))
                if changed:
                    old.update({k: ev[k] for k in ("date", "precision", "time", "note", "title") if k in ev})
                    updated += 1
            continue
        if (ev["date"], norm_title(ev["title"])) in existing_keys:
            continue
        events.append(ev)
        existing_keys.add((ev["date"], norm_title(ev["title"])))
        added += 1

    events.sort(key=lambda e: (e.get("date", "9999"), -int(e.get("importance", 1))))
    payload["updated"] = (dt.datetime.utcnow() + dt.timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    with open(EV, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    log(f"[merge] added {added}, updated {updated}, total {len(events)}")

    os.makedirs(os.path.dirname(LOGF), exist_ok=True)
    with open(LOGF, "w", encoding="utf-8") as f:
        f.write("\n".join(LOG) + "\n")

if __name__ == "__main__":
    main()

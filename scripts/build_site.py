#!/usr/bin/env python3
"""把 data/events.json 嵌入 site/template.html，輸出 build/index.html（未加密版）"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    with open(os.path.join(ROOT, "data", "events.json"), encoding="utf-8") as f:
        payload = json.load(f)
    # 依日期排序
    payload["events"].sort(key=lambda e: (e.get("date", "9999"), -int(e.get("importance", 1))))
    with open(os.path.join(ROOT, "site", "template.html"), encoding="utf-8") as f:
        tpl = f.read()
    marker = "/*__DATA__*/null"
    if marker not in tpl:
        print("ERROR: template marker not found"); sys.exit(1)
    html = tpl.replace(marker, "/*__DATA__*/" + json.dumps(payload, ensure_ascii=False))
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    out = os.path.join(ROOT, "build", "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"built {out} ({len(payload['events'])} events)")

if __name__ == "__main__":
    main()

# future-events 未來事件時間表

投資用未來事件追蹤系統。網頁（加密）：https://kidd0368.github.io/future-events/

## 結構

- `data/events.json` — 事件資料（唯一資料源）
- `data/watchlist.json` — 台股法說會追蹤清單
- `site/template.html` — 時間表網頁模板
- `scripts/fetch_auto.py` — 每日自動抓取（規則事件、台股法說會、金十財經日曆）
- `scripts/build_site.py` — 資料嵌入模板產出 `build/index.html`
- `.github/workflows/daily.yml` — 每日 06:30（台北）自動抓取 → 加密 → 部署 Pages
- `logs/fetch_log.txt` — 最近一次抓取紀錄

## 事件欄位

`precision`: `day`（確定日）/ `month`（僅知月份）/ `quarter` / `year`
`source`: `seed` / `auto:rule` / `auto:twse` / `auto:jin10` / `manual`（手動加入）/ `ai`（AI 掃描）
`tentative`: true = 日期未定或預期

## 更新方式

1. 每日 GitHub Actions 自動抓取
2. Claude 每日 AI 掃描新聞後推送
3. 在 Claude 對話說「加到時間表」＋貼上內容，確認後自動推送

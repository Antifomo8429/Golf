# TWSE 競價拍賣公告 → 自動更新行事曆（.ics）

這個專案會把臺灣證券交易所（TWSE）的「競價拍賣公告－投標日程表」資料，自動轉成可訂閱的行事曆檔案（iCalendar / `.ics`）。

- 資料來源頁面：`https://www.twse.com.tw/zh/announcement/auction.html`
- 使用的資料 API：`https://www.twse.com.tw/announcement/auction?date=YYYY`

## 你會拿到什麼

專案根目錄的 `twse-auction.ics`，內容會包含（以「整天事件」呈現）：

- 投標開始日
- 投標結束日
- 開標日
- 撥券/上市(櫃)日

每個事件會包含證券名稱/代號、發行市場、競拍方式、最低投標價格等資訊。

## 如何訂閱（不需要寫程式）

行事曆 App 通常支援「以網址訂閱 `.ics`」。

1. 先找到這個檔案的 **raw 連結**（格式如下，請把 `<owner>` `<repo>` `<branch>` 換成你的實際值）  
   `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/twse-auction.ics`
2. 在你的行事曆（Google / Apple / Outlook）新增「由網址訂閱」並貼上該連結。

> 若你把分支合併到 `main`，通常就用 `main` 當 `<branch>` 會最穩定。

## 自動更新機制（給想知道原理的人）

`.github/workflows/update-auction-calendar.yml` 會每天排程跑一次，流程是：

1. 執行 `python3 scripts/twse_auction_calendar.py`
2. 產生/更新 `twse-auction.ics`
3. 若檔案有變動，就自動 commit 並 push 回 repo

## 手動更新（本機執行）

你只需要有 Python 3：

```bash
python3 scripts/twse_auction_calendar.py --output twse-auction.ics
```

指定年份（例如抓 2025 與 2026）：

```bash
python3 scripts/twse_auction_calendar.py --years 2025,2026 --output twse-auction.ics
```


# TWSE 競價拍賣公告自動更新行事曆

這個專案會把臺灣證交所「競價拍賣公告」自動轉成可訂閱的行事曆（`.ics` 檔）。

資料來源頁面：
<https://www.twse.com.tw/zh/announcement/auction.html>

---

## 你會得到什麼

- 一個可訂閱的日曆檔：`calendar/twse-auction.ics`
- 每天自動更新（GitHub Actions 排程）
- 事件內容包含：
  - 投標開始日
  - 投標結束日
  - 開標日期
  - 撥券/掛牌日期

---

## 專案內的重要檔案（白話解釋）

- `scripts/generate_twse_auction_calendar.py`  
  抓取證交所資料，轉成 `.ics` 行事曆檔。

- `.github/workflows/update-twse-auction-calendar.yml`  
  GitHub 的自動排程設定。每天會自動執行上面的 Python 程式。

- `calendar/twse-auction.ics`  
  最終可訂閱的日曆檔。

---

## 如何手動產生日曆（一次）

> 如果你只想先試一次，可以在專案根目錄執行：

```bash
python3 scripts/generate_twse_auction_calendar.py --output calendar/twse-auction.ics
```

---

## 如何取得「可訂閱」連結

當這個專案放在 GitHub，且 `calendar/twse-auction.ics` 已存在時，可用下列格式：

```text
https://raw.githubusercontent.com/<你的GitHub帳號>/<你的Repo名稱>/main/calendar/twse-auction.ics
```

把上面 `<...>` 換成你的實際資訊即可。

---

## 匯入到常見行事曆

### Google 日曆
1. 打開 Google Calendar
2. 左側「其他日曆」旁邊按 `+`
3. 選「透過網址新增」
4. 貼上 `.ics` 連結
5. 確認新增

### Apple Calendar（macOS / iOS）
1. 開啟 Calendar
2. 選「新增訂閱行事曆」
3. 貼上 `.ics` 連結
4. 設定更新頻率（建議每天）

---

## 注意事項

- 證交所公告內容若異動，行事曆會在排程後自動更新。
- 日曆平台本身（Google/Apple）可能有自己的快取時間，通常不會立刻反映。
- 資料以證交所公告為準。

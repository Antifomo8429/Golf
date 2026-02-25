# TWSE 競價拍賣行事曆

自動追蹤臺灣證券交易所（TWSE）競價拍賣公告，產生可訂閱的 ICS 行事曆檔案。

## 功能

- 每日自動從 [TWSE 競價拍賣公告](https://www.twse.com.tw/zh/announcement/auction.html) 抓取最新資料
- 產生標準 ICS 行事曆檔案，可匯入 Google Calendar / Apple 行事曆 / Outlook
- 透過 GitHub Pages 提供行事曆訂閱網址，訂閱後自動同步更新
- 涵蓋前一年、當年及隔年的拍賣資料

## 行事曆事件類型

每筆競價拍賣會產生三個行事曆事件：

| 圖示 | 事件類型 | 說明 |
|------|---------|------|
| 📋 | 投標期間 | 可進行投標的日期區間 |
| 🔔 | 開標日 | 公布得標結果的日期 |
| 🎯 | 撥券日 | 上市或上櫃日期 |

已取消或流標的事件會在標題標註【已取消】。

## 訂閱方式

啟用 GitHub Pages 後，可透過以下方式訂閱：

- **Google Calendar**：其他日曆 → 透過網址新增 → 貼上 ICS 網址
- **Apple 行事曆**：檔案 → 新增訂閱行事曆 → 貼上 ICS 網址
- **Outlook**：行事曆 → 新增行事曆 → 從網際網路訂閱 → 貼上 ICS 網址

## 手動執行

```bash
pip install -r requirements.txt
python generate_calendar.py
```

產生的 ICS 檔案位於 `docs/twse-auction.ics`。

## 自動更新

透過 GitHub Actions 每日台灣時間早上 8:00 自動執行，並部署至 GitHub Pages。
也可手動觸發 workflow（Actions → Update TWSE Auction Calendar → Run workflow）。

## 資料來源

- [臺灣證券交易所 競價拍賣公告](https://www.twse.com.tw/zh/announcement/auction.html)

## 免責聲明

本行事曆僅供參考，投資決策請以官方公告為準。

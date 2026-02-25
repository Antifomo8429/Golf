#!/usr/bin/env python3
"""
TWSE 競價拍賣行事曆產生器

從臺灣證券交易所 API 抓取競價拍賣公告資料，
產生 ICS 行事曆檔案，方便訂閱追蹤。
"""

import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

import requests
from icalendar import Calendar, Event

TWSE_API_URL = "https://www.twse.com.tw/announcement/auction"
OUTPUT_DIR = "docs"
ICS_FILENAME = "twse-auction.ics"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.twse.com.tw/zh/announcement/auction.html",
}


def fetch_auction_data(year: int) -> list[dict]:
    """從 TWSE API 抓取指定年份的競價拍賣資料。"""
    params = {"response": "json", "date": str(year)}
    try:
        resp = requests.get(TWSE_API_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"  [警告] 無法取得 {year} 年資料: {e}")
        return []

    if payload.get("stat") != "OK" or not payload.get("data"):
        print(f"  [資訊] {year} 年無資料")
        return []

    fields = payload["fields"]
    rows = []
    for row in payload["data"]:
        rows.append(dict(zip(fields, row)))
    print(f"  [OK] {year} 年共 {len(rows)} 筆")
    return rows


def parse_date(date_str: str) -> date | None:
    """將 YYYY/MM/DD 格式的日期字串轉為 date 物件。"""
    if not date_str or date_str.strip() == "0":
        return None
    try:
        return datetime.strptime(date_str.strip(), "%Y/%m/%d").date()
    except ValueError:
        return None


def clean_number(s: str) -> str:
    """移除數字中的千位分隔逗號。"""
    return re.sub(r",", "", s) if s else s


def make_uid(row: dict, suffix: str) -> str:
    """產生穩定且唯一的事件 UID。"""
    raw = f"{row['證券代號']}-{row['開標日期']}-{suffix}"
    return hashlib.md5(raw.encode()).hexdigest() + "@twse-auction"


def build_calendar(all_rows: list[dict]) -> Calendar:
    """根據抓取的資料建立 ICS 行事曆。"""
    cal = Calendar()
    cal.add("prodid", "-//TWSE Auction Calendar//twse.com.tw//")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "TWSE 競價拍賣行事曆")
    cal.add("x-wr-timezone", "Asia/Taipei")

    now = datetime.now(tz=__import__("zoneinfo").ZoneInfo("UTC"))

    for row in all_rows:
        code = row.get("證券代號", "").strip()
        name = row.get("證券名稱", "").strip()
        market = row.get("發行市場", "").strip()
        nature = row.get("發行性質", "").strip()
        method = row.get("競拍方式", "").strip()
        broker = row.get("主辦券商", "").strip()
        cancelled = row.get("取消競價拍賣(流標或取消)", "").strip()

        bid_start = parse_date(row.get("投標開始日", ""))
        bid_end = parse_date(row.get("投標結束日", ""))
        open_date = parse_date(row.get("開標日期", ""))
        listing_date = parse_date(row.get("撥券日期(上市、上櫃日期)", ""))

        qty = clean_number(row.get("競拍數量(張)", ""))
        min_price = clean_number(row.get("最低投標價格(元)", ""))
        deposit_pct = row.get("保證金成數(%)", "").strip()
        fee = clean_number(row.get("每一投標單投標處理費(元)", ""))

        status_line = f"⚠️ {cancelled}" if cancelled else ""

        description_parts = [
            f"證券代號：{code}",
            f"證券名稱：{name}",
            f"發行市場：{market}",
            f"發行性質：{nature}",
            f"競拍方式：{method}",
            f"主辦券商：{broker}",
            f"競拍數量：{qty} 張",
            f"最低投標價格：{min_price} 元",
            f"保證金成數：{deposit_pct}%",
            f"投標處理費：{fee} 元",
        ]

        if open_date:
            description_parts.append(f"開標日期：{open_date.isoformat()}")
        if listing_date:
            description_parts.append(f"撥券日期：{listing_date.isoformat()}")
        if status_line:
            description_parts.append(status_line)

        description_parts.append(
            f"\n📎 https://www.twse.com.tw/zh/announcement/auction.html"
        )
        description = "\n".join(description_parts)

        cancelled_tag = "【已取消】" if cancelled else ""

        # --- 事件 1：投標期間 (多天全天事件) ---
        if bid_start and bid_end:
            evt = Event()
            evt.add("summary", f"{cancelled_tag}📋 投標｜{name}（{code}）")
            evt.add("dtstart", bid_start)
            evt.add("dtend", bid_end + timedelta(days=1))
            evt.add("description", description)
            evt.add("dtstamp", now)
            evt["uid"] = make_uid(row, "bid")
            evt.add("categories", ["TWSE競價拍賣", "投標期間"])
            if cancelled:
                evt.add("status", "CANCELLED")
            cal.add_component(evt)

        # --- 事件 2：開標日 ---
        if open_date:
            evt = Event()
            evt.add("summary", f"{cancelled_tag}🔔 開標｜{name}（{code}）")
            evt.add("dtstart", open_date)
            evt.add("dtend", open_date + timedelta(days=1))
            evt.add("description", description)
            evt.add("dtstamp", now)
            evt["uid"] = make_uid(row, "open")
            evt.add("categories", ["TWSE競價拍賣", "開標日"])
            if cancelled:
                evt.add("status", "CANCELLED")
            cal.add_component(evt)

        # --- 事件 3：撥券日 / 上市上櫃日 ---
        if listing_date:
            evt = Event()
            evt.add("summary", f"{cancelled_tag}🎯 撥券上市櫃｜{name}（{code}）")
            evt.add("dtstart", listing_date)
            evt.add("dtend", listing_date + timedelta(days=1))
            evt.add("description", description)
            evt.add("dtstamp", now)
            evt["uid"] = make_uid(row, "list")
            evt.add("categories", ["TWSE競價拍賣", "撥券日"])
            if cancelled:
                evt.add("status", "CANCELLED")
            cal.add_component(evt)

    return cal


def main():
    print("=== TWSE 競價拍賣行事曆產生器 ===\n")

    current_year = date.today().year
    years = [current_year - 1, current_year, current_year + 1]

    all_rows = []
    for y in years:
        print(f"正在抓取 {y} 年資料...")
        rows = fetch_auction_data(y)
        all_rows.extend(rows)

    if not all_rows:
        print("\n[錯誤] 沒有取得任何資料，無法產生行事曆。")
        sys.exit(1)

    print(f"\n共取得 {len(all_rows)} 筆拍賣資料")

    cal = build_calendar(all_rows)
    event_count = len([c for c in cal.walk() if c.name == "VEVENT"])
    print(f"已建立 {event_count} 個行事曆事件")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, ICS_FILENAME)
    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"\n行事曆已寫入：{output_path}")
    print("完成！")


if __name__ == "__main__":
    main()

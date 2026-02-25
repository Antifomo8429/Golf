#!/usr/bin/env python3
"""
TWSE 競價拍賣行事曆產生器

從臺灣證券交易所 API 抓取競價拍賣公告資料，
產生 ICS 行事曆檔案，方便訂閱追蹤。
當資料有任何變動時，透過 Discord Webhook 發送通知。
"""

import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar, Event

TWSE_API_URL = "https://www.twse.com.tw/announcement/auction"
OUTPUT_DIR = "docs"
ICS_FILENAME = "twse-auction.ics"
SNAPSHOT_FILE = os.path.join(OUTPUT_DIR, "snapshot.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.twse.com.tw/zh/announcement/auction.html",
}

FIELD_LABELS = {
    "序號": "序號",
    "開標日期": "開標日期",
    "證券名稱": "證券名稱",
    "證券代號": "證券代號",
    "發行市場": "發行市場",
    "發行性質": "發行性質",
    "競拍方式": "競拍方式",
    "投標開始日": "投標開始日",
    "投標結束日": "投標結束日",
    "競拍數量(張)": "競拍數量",
    "最低投標價格(元)": "最低投標價格",
    "最低每標單投標數量(張)": "最低每標單投標數量",
    "最高投(得)標數量(張)": "最高投(得)標數量",
    "保證金成數(%)": "保證金成數",
    "每一投標單投標處理費(元)": "投標處理費",
    "撥券日期(上市、上櫃日期)": "撥券日期",
    "主辦券商": "主辦券商",
    "得標總金額(元)": "得標總金額",
    "得標手續費率(%)": "得標手續費率",
    "總合格件": "總合格件",
    "合格投標數量(張)": "合格投標數量",
    "最低得標價格(元)": "最低得標價格",
    "最高得標價格(元)": "最高得標價格",
    "得標加權平均價格(元)": "得標加權平均價格",
    "實際承銷價格(元)": "實際承銷價格",
    "取消競價拍賣(流標或取消)": "取消競價拍賣",
}


def row_key(row: dict) -> str:
    """用證券代號 + 開標日期作為每筆資料的唯一 key。"""
    return f"{row.get('證券代號', '').strip()}-{row.get('開標日期', '').strip()}"


# ──────────────────────────────────────────────
# 資料抓取
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# 快照比對
# ──────────────────────────────────────────────

def load_snapshot() -> dict[str, dict]:
    """讀取上次儲存的資料快照，回傳 {key: row_dict}。"""
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            rows = json.load(f)
        return {row_key(r): r for r in rows}
    except (json.JSONDecodeError, KeyError):
        return {}


def save_snapshot(all_rows: list[dict]) -> None:
    """將目前資料儲存為快照 JSON。"""
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)


def diff_data(
    old_map: dict[str, dict], new_map: dict[str, dict]
) -> tuple[list[dict], list[dict], list[tuple[dict, list[tuple[str, str, str]]]]]:
    """
    比對新舊資料，回傳：
      - added:   新增的資料列
      - removed: 移除的資料列
      - changed: [(row, [(欄位名, 舊值, 新值), ...])]  有欄位變動的資料列
    """
    old_keys = set(old_map.keys())
    new_keys = set(new_map.keys())

    added = [new_map[k] for k in sorted(new_keys - old_keys)]
    removed = [old_map[k] for k in sorted(old_keys - new_keys)]

    changed = []
    for k in sorted(old_keys & new_keys):
        old_row = old_map[k]
        new_row = new_map[k]
        diffs = []
        all_fields = sorted(set(list(old_row.keys()) + list(new_row.keys())))
        for field in all_fields:
            old_val = old_row.get(field, "").strip()
            new_val = new_row.get(field, "").strip()
            if old_val != new_val:
                label = FIELD_LABELS.get(field, field)
                diffs.append((label, old_val, new_val))
        if diffs:
            changed.append((new_row, diffs))

    return added, removed, changed


# ──────────────────────────────────────────────
# Discord 通知
# ──────────────────────────────────────────────

def send_discord_notification(
    webhook_url: str,
    added: list[dict],
    removed: list[dict],
    changed: list[tuple[dict, list[tuple[str, str, str]]]],
) -> None:
    """透過 Discord Webhook 發送資料變動通知。"""
    if not webhook_url:
        print("[Discord] 未設定 DISCORD_WEBHOOK_URL，跳過通知")
        return

    embeds = []

    # ── 新增的拍賣 ──
    for row in added:
        name = row.get("證券名稱", "").strip()
        code = row.get("證券代號", "").strip()
        nature = row.get("發行性質", "").strip()
        market = row.get("發行市場", "").strip()
        bid_start = row.get("投標開始日", "").strip()
        bid_end = row.get("投標結束日", "").strip()
        open_date = row.get("開標日期", "").strip()
        listing = row.get("撥券日期(上市、上櫃日期)", "").strip()
        qty = row.get("競拍數量(張)", "").strip()
        min_price = row.get("最低投標價格(元)", "").strip()
        broker = row.get("主辦券商", "").strip()

        fields_list = [
            {"name": "發行性質", "value": nature or "-", "inline": True},
            {"name": "發行市場", "value": market or "-", "inline": True},
            {"name": "主辦券商", "value": broker or "-", "inline": True},
            {"name": "投標期間", "value": f"{bid_start} ~ {bid_end}" if bid_start else "-", "inline": True},
            {"name": "開標日期", "value": open_date or "-", "inline": True},
            {"name": "撥券日期", "value": listing or "-", "inline": True},
            {"name": "競拍數量", "value": f"{qty} 張" if qty else "-", "inline": True},
            {"name": "最低投標價格", "value": f"{min_price} 元" if min_price else "-", "inline": True},
        ]

        embeds.append({
            "title": f"🆕 新增拍賣｜{name}（{code}）",
            "color": 0x22C55E,
            "fields": fields_list,
        })

    # ── 欄位變動的拍賣 ──
    for row, diffs in changed:
        name = row.get("證券名稱", "").strip()
        code = row.get("證券代號", "").strip()

        fields_list = []
        for label, old_val, new_val in diffs:
            fields_list.append({
                "name": label,
                "value": f"~~{old_val or '(空)'}~~ → **{new_val or '(空)'}**",
                "inline": True,
            })

        embeds.append({
            "title": f"📝 資料更新｜{name}（{code}）",
            "color": 0x3B82F6,
            "fields": fields_list,
        })

    # ── 移除的拍賣 ──
    for row in removed:
        name = row.get("證券名稱", "").strip()
        code = row.get("證券代號", "").strip()
        embeds.append({
            "title": f"❌ 已移除｜{name}（{code}）",
            "color": 0xEF4444,
            "description": f"開標日期：{row.get('開標日期', '-')}",
        })

    if not embeds:
        return

    total_added = len(added)
    total_changed = len(changed)
    total_removed = len(removed)
    summary = f"新增 {total_added} 筆 ∣ 更新 {total_changed} 筆 ∣ 移除 {total_removed} 筆"

    # Discord 每則訊息最多 10 個 embeds，需要分批送出
    MAX_EMBEDS = 10
    for i in range(0, len(embeds), MAX_EMBEDS):
        batch = embeds[i : i + MAX_EMBEDS]
        payload = {
            "username": "TWSE 競價拍賣通知",
            "avatar_url": "https://www.twse.com.tw/favicon.ico",
            "embeds": batch,
        }
        if i == 0:
            payload["content"] = f"📊 **TWSE 競價拍賣資料變動**\n{summary}"

        try:
            resp = requests.post(webhook_url, json=payload, timeout=15)
            if resp.status_code == 204:
                print(f"[Discord] 第 {i // MAX_EMBEDS + 1} 批通知已送出（{len(batch)} 則）")
            else:
                print(f"[Discord] 送出失敗: HTTP {resp.status_code} - {resp.text[:200]}")
        except requests.RequestException as e:
            print(f"[Discord] 送出錯誤: {e}")


# ──────────────────────────────────────────────
# ICS 行事曆產生
# ──────────────────────────────────────────────

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

    now = datetime.now(tz=ZoneInfo("UTC"))

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


# ──────────────────────────────────────────────
# 主程式
# ──────────────────────────────────────────────

def main():
    print("=== TWSE 競價拍賣行事曆產生器 ===\n")

    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")

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

    # ── 比對快照，偵測變動 ──
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    old_map = load_snapshot()
    new_map = {row_key(r): r for r in all_rows}

    if old_map:
        added, removed, changed = diff_data(old_map, new_map)
        total_changes = len(added) + len(removed) + len(changed)
        if total_changes > 0:
            print(f"\n偵測到 {total_changes} 筆變動（新增 {len(added)}、更新 {len(changed)}、移除 {len(removed)}）")
            send_discord_notification(discord_webhook, added, removed, changed)
        else:
            print("\n資料無變動")
    else:
        print("\n首次執行，建立初始快照（不發送通知）")

    save_snapshot(all_rows)

    # ── 產生行事曆 ──
    cal = build_calendar(all_rows)
    event_count = len([c for c in cal.walk() if c.name == "VEVENT"])
    print(f"已建立 {event_count} 個行事曆事件")

    output_path = os.path.join(OUTPUT_DIR, ICS_FILENAME)
    with open(output_path, "wb") as f:
        f.write(cal.to_ical())

    print(f"\n行事曆已寫入：{output_path}")
    print("完成！")


if __name__ == "__main__":
    main()

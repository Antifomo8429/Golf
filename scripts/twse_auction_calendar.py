#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable


TWSE_BASE_URL = "https://www.twse.com.tw"
TWSE_AUCTION_PAGE_URL = "https://www.twse.com.tw/zh/announcement/auction.html"


@dataclass(frozen=True)
class AuctionRow:
    open_date: dt.date | None  # 開標日期
    name: str  # 證券名稱
    code: str  # 證券代號
    market: str  # 發行市場
    issue_type: str  # 發行性質
    auction_method: str  # 競拍方式
    bid_start: dt.date | None  # 投標開始日
    bid_end: dt.date | None  # 投標結束日
    quantity_lot: str  # 競拍數量(張)
    min_bid_price: str  # 最低投標價格(元)
    min_bid_lot: str  # 最低每標單投標數量(張)
    max_award_lot: str  # 最高投(得)標數量(張)
    margin_rate_pct: str  # 保證金成數(%)
    handling_fee: str  # 每一投標單投標處理費(元)
    allotment_date: dt.date | None  # 撥券日期(上市、上櫃日期)
    lead_underwriter: str  # 主辦券商
    cancel_reason: str  # 取消競價拍賣(流標或取消)


def _fetch_json(path: str, params: dict[str, str]) -> dict:
    url = f"{TWSE_BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    try:
        return json.loads(raw.decode(charset, "replace"))
    except Exception as e:
        raise RuntimeError(f"無法解析 JSON：{url}") from e


def _parse_twse_date(s: str) -> dt.date | None:
    s = (s or "").strip()
    if not s or s in {"0", "-", "--", "N/A"}:
        return None
    try:
        y, m, d = [int(x) for x in s.split("/")]
        return dt.date(y, m, d)
    except Exception:
        return None


def fetch_auction_rows(year: int) -> list[AuctionRow]:
    payload = _fetch_json("/announcement/auction", {"date": str(year)})
    stat = (payload.get("stat") or "").strip()
    if stat != "OK":
        # 常見情況：未來年度尚未有資料，TWSE 會回傳「很抱歉，沒有符合條件的資料!」
        if "沒有符合條件的資料" in stat:
            return []
        raise RuntimeError(f"TWSE 回傳非 OK：{stat}")

    rows: list[AuctionRow] = []
    for r in payload.get("data") or []:
        # 欄位順序（TWSE fields）：
        # 1 開標日期, 2 名稱, 3 代號, 4 市場, 5 性質, 6 競拍方式,
        # 7 投標開始, 8 投標結束, 9 數量, 10 最低投標價, 11 最低每標單,
        # 12 最高投(得)標, 13 保證金成數, 14 處理費, 15 撥券日,
        # 16 主辦券商, 25 取消原因
        def g(i: int) -> str:
            v = r[i] if i < len(r) else ""
            return (v or "").strip()

        rows.append(
            AuctionRow(
                open_date=_parse_twse_date(g(1)),
                name=g(2),
                code=g(3),
                market=g(4),
                issue_type=g(5),
                auction_method=g(6),
                bid_start=_parse_twse_date(g(7)),
                bid_end=_parse_twse_date(g(8)),
                quantity_lot=g(9),
                min_bid_price=g(10),
                min_bid_lot=g(11),
                max_award_lot=g(12),
                margin_rate_pct=g(13),
                handling_fee=g(14),
                allotment_date=_parse_twse_date(g(15)),
                lead_underwriter=g(16),
                cancel_reason=g(25),
            )
        )
    return rows


def _ics_escape_text(s: str) -> str:
    # RFC 5545 TEXT escaping
    s = s.replace("\\", "\\\\")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "\\n")
    s = s.replace(";", "\\;").replace(",", "\\,")
    return s


def _ics_fold_line(line: str) -> str:
    # RFC 5545: lines SHOULD be folded at 75 octets; we fold conservatively by characters.
    # This is widely accepted by calendar clients (Google/Apple/Outlook).
    if len(line) <= 73:
        return line
    out: list[str] = []
    cur = line
    while len(cur) > 73:
        out.append(cur[:73])
        cur = " " + cur[73:]
    out.append(cur)
    return "\r\n".join(out)


def _ics_date(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _ics_dtstamp(now_utc: dt.datetime) -> str:
    return now_utc.strftime("%Y%m%dT%H%M%SZ")


def _event_uid(prefix: str, row: AuctionRow, when: dt.date, kind: str) -> str:
    safe_code = row.code or "UNKNOWN"
    return f"{prefix}-{kind}-{safe_code}-{when.strftime('%Y%m%d')}@twse.com.tw"


def _build_all_day_event(
    *,
    uid: str,
    dtstamp_utc: dt.datetime,
    date: dt.date,
    summary: str,
    description: str,
    url: str,
    status: str | None = None,
) -> list[str]:
    lines: list[str] = [
        "BEGIN:VEVENT",
        f"UID:{_ics_escape_text(uid)}",
        f"DTSTAMP:{_ics_dtstamp(dtstamp_utc)}",
        f"DTSTART;VALUE=DATE:{_ics_date(date)}",
        f"DTEND;VALUE=DATE:{_ics_date(date + dt.timedelta(days=1))}",
        f"SUMMARY:{_ics_escape_text(summary)}",
        f"DESCRIPTION:{_ics_escape_text(description)}",
        f"URL:{_ics_escape_text(url)}",
        "TRANSP:TRANSPARENT",
    ]
    if status:
        lines.append(f"STATUS:{status}")
    lines.append("END:VEVENT")
    return lines


def _row_common_description(row: AuctionRow) -> str:
    parts = [
        f"證券名稱：{row.name}",
        f"證券代號：{row.code}",
        f"發行市場：{row.market}",
        f"發行性質：{row.issue_type}",
        f"競拍方式：{row.auction_method}",
        f"競拍數量(張)：{row.quantity_lot}",
        f"最低投標價格(元)：{row.min_bid_price}",
        f"最低每標單投標數量(張)：{row.min_bid_lot}",
        f"最高投(得)標數量(張)：{row.max_award_lot}",
        f"保證金成數(%)：{row.margin_rate_pct}",
        f"每一投標單投標處理費(元)：{row.handling_fee}",
        f"主辦券商：{row.lead_underwriter}",
    ]
    if row.cancel_reason:
        parts.append(f"取消競價拍賣：{row.cancel_reason}")
    parts.append(f"資料來源：{TWSE_AUCTION_PAGE_URL}")
    return "\n".join(parts)


def rows_to_ics_events(prefix: str, rows: Iterable[AuctionRow], dtstamp_utc: dt.datetime) -> list[str]:
    events: list[str] = []
    for row in rows:
        base_title = f"競價拍賣：{row.name}({row.code})"
        common_desc = _row_common_description(row)
        status = "CANCELLED" if row.cancel_reason else None

        def add(kind: str, when: dt.date | None, suffix: str, extra: str | None = None) -> None:
            if not when:
                return
            desc = common_desc
            if extra:
                desc = f"{extra}\n\n{common_desc}"
            events.extend(
                _build_all_day_event(
                    uid=_event_uid(prefix, row, when, kind),
                    dtstamp_utc=dtstamp_utc,
                    date=when,
                    summary=f"{base_title} {suffix}",
                    description=desc,
                    url=TWSE_AUCTION_PAGE_URL,
                    status=status,
                )
            )

        if row.bid_start and row.bid_end:
            bid_range = f"投標期間：{row.bid_start.strftime('%Y/%m/%d')} ~ {row.bid_end.strftime('%Y/%m/%d')}"
        else:
            bid_range = None

        add("BIDSTART", row.bid_start, "投標開始", bid_range)
        add("BIDEND", row.bid_end, "投標結束", bid_range)
        add("OPEN", row.open_date, "開標日", bid_range)
        add("ALLOT", row.allotment_date, "撥券/上市(櫃)日", bid_range)
    return events


def build_ics_calendar(*, cal_name: str, events: list[str], dtstamp_utc: dt.datetime) -> str:
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"PRODID:-//twse-auction-calendar//twse-auction-calendar//ZH-HANT",
        f"X-WR-CALNAME:{_ics_escape_text(cal_name)}",
        "X-WR-TIMEZONE:Asia/Taipei",
        f"X-PUBLISHED-TTL:PT6H",
    ]
    footer = ["END:VCALENDAR"]

    lines = header + events + footer
    # fold + CRLF
    folded = [_ics_fold_line(l) for l in lines]
    return "\r\n".join(folded) + "\r\n"


def _default_years(today: dt.date) -> list[int]:
    return [today.year, today.year + 1]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="產生 TWSE 競價拍賣日程 iCalendar (.ics)。資料來源：TWSE /announcement/auction?date=YYYY"
    )
    parser.add_argument(
        "--years",
        default="",
        help="要抓的年份（逗號分隔），例如：2025,2026。未指定則抓「今年+明年」。",
    )
    parser.add_argument(
        "--output",
        default="twse-auction.ics",
        help="輸出 .ics 檔案路徑（預設：twse-auction.ics）。",
    )
    parser.add_argument(
        "--uid-prefix",
        default="twse-auction",
        help="UID 前綴（用於避免不同日曆互相衝突）。",
    )
    args = parser.parse_args(argv)

    today = dt.date.today()
    years: list[int]
    if args.years.strip():
        years = [int(x.strip()) for x in args.years.split(",") if x.strip()]
    else:
        years = _default_years(today)

    dtstamp_utc = dt.datetime.now(dt.UTC)
    all_rows: list[AuctionRow] = []
    for y in years:
        all_rows.extend(fetch_auction_rows(y))

    events = rows_to_ics_events(args.uid_prefix, all_rows, dtstamp_utc)
    ics = build_ics_calendar(
        cal_name="TWSE 競價拍賣日程（自動更新）",
        events=events,
        dtstamp_utc=dtstamp_utc,
    )

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        f.write(ics)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


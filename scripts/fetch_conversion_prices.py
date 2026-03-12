#!/usr/bin/env python3
"""Fetch conversion prices (轉換價) for convertible bonds from twsa.org.tw auction PDFs.

Outputs: scripts/conversion_prices.json
  [
    {
      "company": "...",
      "bid_start": "YYYY/MM/DD",
      "bid_end": "YYYY/MM/DD",
      "min_price": "...",
      "conversion_price": "..."
    },
    ...
  ]

Match key used by generate_twse_auction_calendar.py: bid_start + bid_end
"""

from __future__ import annotations

import io
import json
import re
import time
import datetime
from html.parser import HTMLParser
from pathlib import Path

import requests
from pdfminer.high_level import extract_text

BASE_URL = "https://web.twsa.org.tw/EDOC2/"
LIST_URL = BASE_URL + "default.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": LIST_URL,
}

CONVERSION_PRICE_PATTERNS = [
    re.compile(r"轉換價格[：:]\s*([\d,]+(?:\.\d+)?)\s*元"),
    re.compile(r"每股轉換價格[：:]\s*([\d,]+(?:\.\d+)?)\s*元?"),
    re.compile(r"轉換價格\s+([\d,]+(?:\.\d+)?)"),
    re.compile(r"轉換價[：:]\s*([\d,]+(?:\.\d+)?)\s*元?"),
]

OUTPUT_PATH = Path(__file__).parent / "conversion_prices.json"


class _FormParser(HTMLParser):
    """Extract ASP.NET hidden form fields and GridView table rows."""

    def __init__(self) -> None:
        super().__init__()
        self.hidden: dict[str, str] = {}
        self.rows: list[dict] = []
        self._in_grid = False
        self._capture_td = False
        self._current_cell = ""
        self._row_cells: list[str] = []
        self._row_btn: str = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr = dict(attrs)
        if tag == "input":
            if attr.get("type") == "hidden":
                name = attr.get("name", "")
                if name:
                    self.hidden[name] = attr.get("value", "")
            elif attr.get("type") == "image":
                name = attr.get("name", "")
                if "imgbtnAuctionFileName" in name and not self._row_btn:
                    self._row_btn = name
        if tag == "table" and attr.get("id", "").endswith("gvResult"):
            self._in_grid = True
        if self._in_grid:
            if tag == "tr":
                self._row_cells = []
                self._row_btn = ""
            elif tag == "td":
                self._capture_td = True
                self._current_cell = ""

    def handle_endtag(self, tag: str) -> None:
        if not self._in_grid:
            return
        if tag == "td" and self._capture_td:
            self._capture_td = False
            self._row_cells.append(self._current_cell.strip())
        elif tag == "tr":
            cells = self._row_cells
            # Expected columns: 序號, 發行公司, 主辦承銷商, 發行性質, 承銷股數, 競拍股數, 投標期間, 最低承銷價格, 公告檔, 開標統計表
            if len(cells) >= 8 and self._row_btn:
                period = cells[6]  # "2026/01/05~2026/01/07"
                bid_start, _, bid_end = period.partition("~")
                self.rows.append({
                    "company": cells[1],
                    "issue_type": cells[3],
                    "bid_start": bid_start.strip(),
                    "bid_end": bid_end.strip(),
                    "min_price": cells[7],
                    "btn_name": self._row_btn,
                })
        elif tag == "table" and self._in_grid:
            self._in_grid = False

    def handle_data(self, data: str) -> None:
        if self._capture_td:
            self._current_cell += data


def _parse_page(html: str) -> tuple[dict[str, str], list[dict]]:
    parser = _FormParser()
    parser.feed(html)
    return parser.hidden, parser.rows


def _extract_conversion_price(pdf_bytes: bytes) -> str | None:
    try:
        text = extract_text(io.BytesIO(pdf_bytes))
    except Exception:
        return None
    for pattern in CONVERSION_PRICE_PATTERNS:
        m = pattern.search(text)
        if m:
            price_str = m.group(1).replace(",", "")
            try:
                if float(price_str) > 1:
                    return price_str
            except ValueError:
                continue
    return None


def _download_pdf(
    session: requests.Session,
    hidden: dict[str, str],
    btn_name: str,
) -> tuple[bytes | None, dict[str, str]]:
    """POST form to download PDF. Returns (pdf_bytes_or_None, updated_hidden_fields)."""
    form_data = dict(hidden)
    form_data[btn_name + ".x"] = "10"
    form_data[btn_name + ".y"] = "10"
    form_data["ctl00$cphMain$rblReportType"] = "Auction"
    pdf_bytes = None
    new_hidden = hidden

    try:
        # Use allow_redirects=False so we can distinguish redirect vs HTML response
        resp = session.post(
            LIST_URL,
            data=form_data,
            headers=HEADERS,
            timeout=30,
            allow_redirects=False,
        )
        print(f"    POST status={resp.status_code} url={resp.url}")

        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            print(f"    重定向至: {location[:120]}")
            if location:
                dl = session.get(location, headers={**HEADERS, "Referer": LIST_URL}, timeout=30)
                print(f"    下載 status={dl.status_code} type={dl.headers.get('Content-Type','')[:60]}")
                if dl.content[:4] == b"%PDF":
                    pdf_bytes = dl.content
                    print(f"    PDF 成功 ({len(pdf_bytes)} bytes)")
                else:
                    print(f"    非 PDF，前100字: {dl.text[:100]}")
            # Re-fetch listing page to get fresh VIEWSTATE
            try:
                refresh = session.get(LIST_URL, headers=HEADERS, timeout=30)
                new_hidden, _ = _parse_page(refresh.text)
            except Exception:
                pass

        elif resp.content[:4] == b"%PDF" or "pdf" in resp.headers.get("Content-Type", ""):
            pdf_bytes = resp.content
            print(f"    直接 PDF ({len(pdf_bytes)} bytes)")
            try:
                refresh = session.get(LIST_URL, headers=HEADERS, timeout=30)
                new_hidden, _ = _parse_page(refresh.text)
            except Exception:
                pass

        else:
            # Server returned HTML — parse for new VIEWSTATE
            ct = resp.headers.get("Content-Type", "")
            print(f"    非 PDF 回應: type={ct[:60]}")
            print(f"    前200字: {resp.text[:200]}")
            new_hidden, _ = _parse_page(resp.text)

    except Exception as exc:
        print(f"    下載失敗: {exc}")

    return pdf_bytes, new_hidden


def _get_year_page(session: requests.Session, roc_year: int) -> tuple[str, dict[str, str], list[dict]]:
    """Fetch listing page for the given ROC year, handling ASP.NET year postback."""
    ce_year = str(roc_year + 1911)

    resp = session.get(LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    hidden, rows = _parse_page(resp.text)

    if hidden.get("ctl00$cphMain$ddlYear") != ce_year:
        form_data = dict(hidden)
        form_data["__EVENTTARGET"] = "ctl00$cphMain$ddlYear"
        form_data["__EVENTARGUMENT"] = ""
        form_data["ctl00$cphMain$ddlYear"] = ce_year
        form_data["ctl00$cphMain$rblReportType"] = "Auction"
        resp = session.post(LIST_URL, data=form_data, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        hidden, rows = _parse_page(resp.text)

    return resp.text, hidden, rows


def fetch_year(session: requests.Session, roc_year: int) -> list[dict]:
    print(f"正在抓取民國 {roc_year} 年競拍公告...")
    try:
        _, hidden, rows = _get_year_page(session, roc_year)
    except Exception as exc:
        print(f"  無法取得列表: {exc}")
        return []

    convertible_rows = [r for r in rows if "轉換公司債" in r.get("issue_type", "")]
    print(f"  找到 {len(convertible_rows)} 筆可轉債（共 {len(rows)} 筆）")

    results: list[dict] = []
    for row in convertible_rows:
        company = row["company"]
        print(f"  處理: {company} {row['bid_start']}~{row['bid_end']} ...")

        pdf_bytes, hidden = _download_pdf(session, hidden, row["btn_name"])
        if pdf_bytes is None:
            print(f"    -> 無法下載 PDF，跳過")
            results.append({
                "company": company,
                "bid_start": row["bid_start"],
                "bid_end": row["bid_end"],
                "min_price": row["min_price"],
                "conversion_price": None,
            })
            time.sleep(1)
            continue

        price = _extract_conversion_price(pdf_bytes)
        print(f"    -> 轉換價: {price or '未找到'}")
        results.append({
            "company": company,
            "bid_start": row["bid_start"],
            "bid_end": row["bid_end"],
            "min_price": row["min_price"],
            "conversion_price": price,
        })
        time.sleep(1)

    return results


def main() -> int:
    roc_year = datetime.date.today().year - 1911

    session = requests.Session()
    session.headers.update(HEADERS)

    new_entries = fetch_year(session, roc_year)

    # Merge: keep existing entries for other years, replace current year
    existing: list[dict] = []
    if OUTPUT_PATH.exists():
        try:
            existing = json.loads(OUTPUT_PATH.read_text("utf-8"))
        except Exception:
            pass

    # Remove old entries for same year (by bid_start year)
    year_prefix = str(roc_year + 1911) + "/"
    kept = [e for e in existing if not e.get("bid_start", "").startswith(year_prefix)]
    merged = kept + new_entries

    OUTPUT_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with_price = sum(1 for e in merged if e.get("conversion_price"))
    print(f"\n完成：{len(merged)} 筆資料（{with_price} 筆有轉換價），存至 {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

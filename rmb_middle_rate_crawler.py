#!/usr/bin/env python3
"""抓取 SAFE 人民币汇率中间价并输出人民币兑其他币种的一维表。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

SOURCE_PAGE_URL = "https://www.safe.gov.cn/safe/rmbhlzjj/index.html"
DEFAULT_QUERY_URL = "https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do"

CURRENCY_NAME_TO_CODE = {
    "美元": "USD",
    "欧元": "EUR",
    "日元": "JPY",
    "港元": "HKD",
    "英镑": "GBP",
    "澳元": "AUD",
    "新西兰元": "NZD",
    "新加坡元": "SGD",
    "瑞士法郎": "CHF",
    "加元": "CAD",
    "澳门元": "MOP",
    "林吉特": "MYR",
    "卢布": "RUB",
    "兰特": "ZAR",
    "韩元": "KRW",
    "迪拉姆": "AED",
    "里亚尔": "SAR",
    "福林": "HUF",
    "兹罗提": "PLN",
    "丹麦克朗": "DKK",
    "瑞典克朗": "SEK",
    "挪威克朗": "NOK",
    "里拉": "TRY",
    "比索": "MXN",
    "泰铢": "THB",
}

INDIRECT_QUOTES = {
    "MOP",
    "MYR",
    "RUB",
    "ZAR",
    "KRW",
    "AED",
    "SAR",
    "HUF",
    "PLN",
    "DKK",
    "SEK",
    "NOK",
    "TRY",
    "MXN",
    "THB",
}

TABLE_RE = re.compile(r'<table[^>]*id="InfoTable"[^>]*>(.*?)</table>', re.S | re.I)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 SAFE 人民币汇率中间价，输出一维 CSV。")
    parser.add_argument("--range", dest="date_range", help="数据区间，格式 START:END")
    parser.add_argument("--start-date", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=365, help="未指定区间时默认回溯天数")
    parser.add_argument("--url", default=DEFAULT_QUERY_URL, help="SAFE 查询接口地址")
    parser.add_argument("--timeout", type=float, default=15.0, help="单次请求超时秒数")
    parser.add_argument("--sleep", type=float, default=0.0, help="分段抓取间隔秒数")
    parser.add_argument("--symbols", default="", help="币种代码列表，如 USD,EUR")
    parser.add_argument("--output", default="rmb_rates.csv", help="输出 CSV 路径")
    return parser.parse_args()


def parse_date(date_str: str) -> dt.date:
    return dt.datetime.strptime(date_str, "%Y-%m-%d").date()


def resolve_date_window(args: argparse.Namespace) -> Tuple[dt.date, dt.date]:
    if args.date_range:
        if args.start_date or args.end_date:
            raise ValueError("使用 --range 时，不应再传 --start-date/--end-date")
        if ":" not in args.date_range:
            raise ValueError("--range 格式错误，应为 START:END")
        start_s, end_s = [x.strip() for x in args.date_range.split(":", 1)]
        return parse_date(start_s), parse_date(end_s)

    if bool(args.start_date) ^ bool(args.end_date):
        raise ValueError("--start-date 与 --end-date 需要同时提供")

    if args.start_date and args.end_date:
        return parse_date(args.start_date), parse_date(args.end_date)

    if args.days < 1:
        raise ValueError("--days 必须 >= 1")
    end = dt.date.today()
    start = end - dt.timedelta(days=args.days)
    return start, end


def split_into_chunks(start: dt.date, end: dt.date, max_span_days: int = 92) -> List[Tuple[dt.date, dt.date]]:
    chunks: List[Tuple[dt.date, dt.date]] = []
    cur = start
    while cur <= end:
        seg_end = min(cur + dt.timedelta(days=max_span_days - 1), end)
        chunks.append((cur, seg_end))
        cur = seg_end + dt.timedelta(days=1)
    return chunks


def clean_text(cell_html: str) -> str:
    text = TAG_RE.sub("", cell_html)
    text = html.unescape(text)
    return text.replace("\xa0", " ").replace("-->", "").strip()


def http_post_html(url: str, payload: Dict[str, str], timeout: float) -> str:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RMBFxCrawler/1.0)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": SOURCE_PAGE_URL,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    return body.decode("utf-8", errors="ignore")


def parse_safe_table(html_text: str, symbols: List[str]) -> Dict[str, Dict[str, float]]:
    wanted = set(symbols) if symbols else set(CURRENCY_NAME_TO_CODE.values())
    out: Dict[str, Dict[str, float]] = {}
    table_match = TABLE_RE.search(html_text)
    if not table_match:
        return out

    rows = ROW_RE.findall(table_match.group(1))
    headers: List[str] = []
    for row_html in rows:
        cells = [clean_text(x) for x in CELL_RE.findall(row_html)]
        if not cells:
            continue
        if "日期" in cells and any(name in CURRENCY_NAME_TO_CODE for name in cells):
            headers = cells
            continue
        if not headers:
            continue

        day = cells[0]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            continue

        daily = out.setdefault(day, {})
        for idx, header in enumerate(headers[1:], start=1):
            if idx >= len(cells):
                continue
            code = CURRENCY_NAME_TO_CODE.get(header)
            if not code or code not in wanted:
                continue
            raw = cells[idx].replace(",", "")
            if not raw or raw == "-":
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if value <= 0:
                continue
            if code in INDIRECT_QUOTES:
                daily[code] = value / 100.0
            else:
                daily[code] = 100.0 / value
    return out


def fetch_rates_with_auto_chunk(
    url: str,
    start: dt.date,
    end: dt.date,
    symbols: List[str],
    timeout: float,
    sleep_s: float,
) -> Dict[str, Dict[str, float]]:
    chunks = split_into_chunks(start, end, max_span_days=92)
    if len(chunks) > 1:
        print(f"[INFO] 区间超过3个月，自动拆分为 {len(chunks)} 段抓取并拼接。")

    merged: Dict[str, Dict[str, float]] = {}
    for idx, (seg_start, seg_end) in enumerate(chunks, start=1):
        payload = {
            "startDate": seg_start.strftime("%Y-%m-%d"),
            "endDate": seg_end.strftime("%Y-%m-%d"),
            "queryYN": "true",
        }
        try:
            html_text = http_post_html(url, payload, timeout=timeout)
            piece = parse_safe_table(html_text, symbols)
            merged.update(piece)
            print(f"[INFO] 分段 {idx}/{len(chunks)}: {seg_start} ~ {seg_end}, 获取 {len(piece)} 个交易日")
        except Exception as exc:
            print(f"[WARN] 分段 {seg_start} ~ {seg_end} 抓取失败: {exc}", file=sys.stderr)
        time.sleep(max(sleep_s, 0.0))

    return merged


def build_rmb_rows(day_to_rates: Dict[str, Dict[str, float]]) -> List[Tuple[str, str, str, float]]:
    rows: List[Tuple[str, str, str, float]] = []
    for day in sorted(day_to_rates.keys()):
        for ccy in sorted(day_to_rates[day].keys()):
            rows.append((day, "CNY", ccy, day_to_rates[day][ccy]))
    return rows


def write_rmb_csv(path: str, rows: List[Tuple[str, str, str, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "from_currency", "to_currency", "rate"])
        for day, src, dst, rate in rows:
            w.writerow([day, src, dst, f"{rate:.10f}"])


def main() -> int:
    args = parse_args()
    try:
        start, end = resolve_date_window(args)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if start > end:
        print("[ERROR] start-date 不能晚于 end-date", file=sys.stderr)
        return 1

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print(f"数据源页面: {SOURCE_PAGE_URL}")
    print(f"抓取区间: {start} ~ {end}")
    day_to_rates = fetch_rates_with_auto_chunk(
        url=args.url,
        start=start,
        end=end,
        symbols=symbols,
        timeout=args.timeout,
        sleep_s=args.sleep,
    )

    rows = build_rmb_rows(day_to_rates)
    write_rmb_csv(args.output, rows)
    print(f"已写出人民币一维汇率表: {args.output} ({len(rows)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""抓取近一年人民币中间价并输出币种间换算汇率二维表。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew"
PAIR_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)?\s*([A-Za-z]{3})\s*/\s*([A-Za-z]{3})\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取近1年人民币中间价，并输出各币种之间的换算汇率（CSV二维表）。"
    )
    parser.add_argument("--start-date", help="开始日期，格式 YYYY-MM-DD；默认今天往前1年")
    parser.add_argument("--end-date", help="结束日期，格式 YYYY-MM-DD；默认今天")
    parser.add_argument("--url", default=DEFAULT_URL, help="中间价数据接口地址")
    parser.add_argument("--sleep", type=float, default=0.2, help="按天抓取时每次请求间隔秒数")
    parser.add_argument(
        "--output",
        default="cross_rates.csv",
        help="输出CSV文件路径（列：date,from_currency,to_currency,rate）",
    )
    parser.add_argument(
        "--latest-matrix-output",
        default="latest_matrix.csv",
        help="输出最新交易日矩阵CSV（二维表）路径",
    )
    parser.add_argument(
        "--raw-output",
        default="raw_middle_rates.csv",
        help="输出原始中间价CSV路径（列：date,pair,value）",
    )
    return parser.parse_args()


def parse_date(date_str: str) -> dt.date:
    return dt.datetime.strptime(date_str, "%Y-%m-%d").date()


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def http_get_json(url: str, params: Dict[str, str]) -> dict:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RMBMiddleRateBot/1.0)",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.chinamoney.com.cn/",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    for enc in ("utf-8", "gbk"):
        try:
            return json.loads(data.decode(enc))
        except Exception:
            continue
    return json.loads(data.decode("utf-8", errors="ignore"))


def collect_record_list(payload: object) -> List[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    common_keys = ("records", "data", "result", "items", "list")
    for k in common_keys:
        v = payload.get(k)
        if isinstance(v, list):
            return [item for item in v if isinstance(item, dict)]
        if isinstance(v, dict):
            for kk in common_keys:
                vv = v.get(kk)
                if isinstance(vv, list):
                    return [item for item in vv if isinstance(item, dict)]

    for v in payload.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return [item for item in v if isinstance(item, dict)]
    return []


def try_parse_float(x: object) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_date(record: dict) -> Optional[str]:
    for key in ("date", "tradeDate", "valueDate", "pubDate"):
        if key in record and str(record[key]).strip():
            value = str(record[key]).strip()
            value = value[:10]
            try:
                parse_date(value)
                return value
            except ValueError:
                continue
    return None


def extract_pair(record: dict) -> Optional[str]:
    for key in ("ccyPair", "pair", "currencyPair", "ccy", "symbol", "name"):
        if key in record:
            pair = str(record[key]).strip().upper().replace("-", "/")
            if "/" in pair:
                return pair
    return None


def extract_value(record: dict) -> Optional[float]:
    for key in ("middlePrice", "price", "value", "mid", "rate"):
        if key in record:
            f = try_parse_float(record[key])
            if f is not None:
                return f
    for v in record.values():
        f = try_parse_float(v)
        if f is not None and f > 0:
            return f
    return None


def parse_pair(pair: str) -> Optional[Tuple[str, str, float]]:
    m = PAIR_RE.match(pair)
    if not m:
        return None
    unit = float(m.group(1)) if m.group(1) else 1.0
    c1 = m.group(2)
    c2 = m.group(3)
    return c1, c2, unit


def to_cny_per_currency(pair: str, value: float) -> Optional[Tuple[str, float]]:
    parsed = parse_pair(pair)
    if not parsed:
        return None
    left, right, unit = parsed
    if value <= 0 or unit <= 0:
        return None

    if right == "CNY":
        # unit left = value CNY
        return left, value / unit
    if left == "CNY":
        # unit CNY = value right  => 1 right = unit/value CNY
        return right, unit / value
    return None


def fetch_by_day(url: str, start: dt.date, end: dt.date, sleep_s: float) -> List[dict]:
    records: List[dict] = []
    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        params = {
            "lang": "cn",
            "startDate": day,
            "endDate": day,
            "pageSize": "2000",
            "pageNum": "1",
        }
        try:
            payload = http_get_json(url, params)
            batch = collect_record_list(payload)
            records.extend(batch)
        except Exception as exc:
            print(f"[WARN] {day} 抓取失败: {exc}", file=sys.stderr)
        time.sleep(max(sleep_s, 0))
    return records


def normalize(records: List[dict]) -> Tuple[List[Tuple[str, str, float]], Dict[str, Dict[str, float]]]:
    raw_rows: List[Tuple[str, str, float]] = []
    day_currency_to_cny: Dict[str, Dict[str, float]] = {}

    for record in records:
        date = extract_date(record)
        pair = extract_pair(record)
        value = extract_value(record)
        if not date or not pair or value is None:
            continue
        raw_rows.append((date, pair, value))

        converted = to_cny_per_currency(pair, value)
        if not converted:
            continue
        ccy, cny_per_unit = converted

        day_map = day_currency_to_cny.setdefault(date, {"CNY": 1.0})
        day_map[ccy] = cny_per_unit

    return raw_rows, day_currency_to_cny


def build_cross_rows(day_currency_to_cny: Dict[str, Dict[str, float]]) -> List[Tuple[str, str, str, float]]:
    rows: List[Tuple[str, str, str, float]] = []
    for date in sorted(day_currency_to_cny.keys()):
        cny_map = day_currency_to_cny[date]
        currencies = sorted(cny_map.keys())
        for src in currencies:
            for dst in currencies:
                rate = cny_map[src] / cny_map[dst]
                if math.isfinite(rate):
                    rows.append((date, src, dst, rate))
    return rows


def write_raw_csv(path: str, rows: List[Tuple[str, str, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "pair", "value"])
        w.writerows(rows)


def write_cross_csv(path: str, rows: List[Tuple[str, str, str, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "from_currency", "to_currency", "rate"])
        for date, src, dst, rate in rows:
            w.writerow([date, src, dst, f"{rate:.10f}"])


def write_latest_matrix_csv(path: str, day_currency_to_cny: Dict[str, Dict[str, float]]) -> Optional[str]:
    if not day_currency_to_cny:
        return None
    latest = sorted(day_currency_to_cny.keys())[-1]
    cny_map = day_currency_to_cny[latest]
    currencies = sorted(cny_map.keys())

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([latest] + currencies)
        for src in currencies:
            row = [src]
            for dst in currencies:
                row.append(f"{(cny_map[src] / cny_map[dst]):.10f}")
            w.writerow(row)
    return latest


def main() -> int:
    args = parse_args()
    end = parse_date(args.end_date) if args.end_date else dt.date.today()
    start = parse_date(args.start_date) if args.start_date else (end - dt.timedelta(days=365))

    if start > end:
        print("[ERROR] start-date 不能晚于 end-date", file=sys.stderr)
        return 1

    print(f"抓取区间: {start} ~ {end}")
    records = fetch_by_day(args.url, start, end, args.sleep)
    print(f"抓取到原始记录数: {len(records)}")

    raw_rows, day_currency_to_cny = normalize(records)
    cross_rows = build_cross_rows(day_currency_to_cny)

    write_raw_csv(args.raw_output, raw_rows)
    write_cross_csv(args.output, cross_rows)
    latest = write_latest_matrix_csv(args.latest_matrix_output, day_currency_to_cny)

    print(f"已写出原始中间价: {args.raw_output} ({len(raw_rows)} 行)")
    print(f"已写出换算汇率: {args.output} ({len(cross_rows)} 行)")
    if latest:
        print(f"已写出最新交易日二维矩阵: {args.latest_matrix_output} (date={latest})")
    else:
        print("[WARN] 未生成最新交易日矩阵（可能没有可解析的数据）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""抓取人民币参考汇率并输出币种间换算汇率二维表。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_URL = "https://api.frankfurter.app"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取人民币参考汇率，并输出各币种之间的换算汇率（CSV二维表）。"
    )
    parser.add_argument(
        "--range",
        dest="date_range",
        help="数据区间（必填推荐），格式 START:END，如 2025-01-01:2025-12-31",
    )
    parser.add_argument("--start-date", help="开始日期，格式 YYYY-MM-DD（与 --range 二选一）")
    parser.add_argument("--end-date", help="结束日期，格式 YYYY-MM-DD（与 --range 二选一）")
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="当未提供 --range 且未同时提供 start/end 时，默认回溯天数（默认 365）",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="汇率接口基础地址")
    parser.add_argument(
        "--symbols",
        default="",
        help="可选：指定币种列表（逗号分隔，如 USD,EUR,JPY）；为空则使用接口返回的全部币种",
    )
    parser.add_argument("--sleep", type=float, default=0.0, help="请求间隔秒数")
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
        help="输出原始参考汇率CSV路径（列：date,base_currency,currency,rate）",
    )
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
        start = parse_date(start_s)
        end = parse_date(end_s)
        return start, end

    if bool(args.start_date) ^ bool(args.end_date):
        raise ValueError("--start-date 与 --end-date 需要同时提供")

    if args.start_date and args.end_date:
        return parse_date(args.start_date), parse_date(args.end_date)

    if args.days < 1:
        raise ValueError("--days 必须 >= 1")
    end = dt.date.today()
    start = end - dt.timedelta(days=args.days)
    return start, end


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
            "User-Agent": "Mozilla/5.0 (compatible; RMBFxCrawler/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def fetch_daily_rates(
    base_url: str,
    start: dt.date,
    end: dt.date,
    symbols: List[str],
    sleep_s: float,
) -> Dict[str, Dict[str, float]]:
    day_currency_to_cny: Dict[str, Dict[str, float]] = {}
    symbols_q = ",".join(symbols) if symbols else ""

    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        url = f"{base_url.rstrip('/')}/{day}"
        params = {"from": "CNY"}
        if symbols_q:
            params["to"] = symbols_q

        try:
            payload = http_get_json(url, params)
            rates = payload.get("rates", {})
            if not isinstance(rates, dict):
                rates = {}

            ccy_map: Dict[str, float] = {"CNY": 1.0}
            for ccy, val in rates.items():
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    continue
                if v <= 0:
                    continue
                ccy_map[ccy.upper()] = 1.0 / v

            if len(ccy_map) > 1:
                day_currency_to_cny[day] = ccy_map
        except Exception as exc:
            print(f"[WARN] {day} 抓取失败: {exc}", file=sys.stderr)

        time.sleep(max(sleep_s, 0.0))

    return day_currency_to_cny


def build_raw_rows(day_currency_to_cny: Dict[str, Dict[str, float]]) -> List[Tuple[str, str, str, float]]:
    rows: List[Tuple[str, str, str, float]] = []
    for day in sorted(day_currency_to_cny.keys()):
        ccy_map = day_currency_to_cny[day]
        for ccy in sorted(ccy_map.keys()):
            if ccy == "CNY":
                continue
            rows.append((day, "CNY", ccy, 1.0 / ccy_map[ccy]))
    return rows


def build_cross_rows(day_currency_to_cny: Dict[str, Dict[str, float]]) -> List[Tuple[str, str, str, float]]:
    rows: List[Tuple[str, str, str, float]] = []
    for date in sorted(day_currency_to_cny.keys()):
        cny_map = day_currency_to_cny[date]
        currencies = sorted(cny_map.keys())
        for src in currencies:
            for dst in currencies:
                rows.append((date, src, dst, cny_map[src] / cny_map[dst]))
    return rows


def write_raw_csv(path: str, rows: List[Tuple[str, str, str, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "base_currency", "currency", "rate"])
        for date, base, ccy, rate in rows:
            w.writerow([date, base, ccy, f"{rate:.10f}"])


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
    try:
        start, end = resolve_date_window(args)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    if start > end:
        print("[ERROR] start-date 不能晚于 end-date", file=sys.stderr)
        return 1

    print(f"抓取区间: {start} ~ {end}")
    day_currency_to_cny = fetch_daily_rates(args.url, start, end, symbols, args.sleep)

    raw_rows = build_raw_rows(day_currency_to_cny)
    cross_rows = build_cross_rows(day_currency_to_cny)

    write_raw_csv(args.raw_output, raw_rows)
    write_cross_csv(args.output, cross_rows)
    latest = write_latest_matrix_csv(args.latest_matrix_output, day_currency_to_cny)

    print(f"已写出原始参考汇率: {args.raw_output} ({len(raw_rows)} 行)")
    print(f"已写出换算汇率: {args.output} ({len(cross_rows)} 行)")
    if latest:
        print(f"已写出最新交易日二维矩阵: {args.latest_matrix_output} (date={latest})")
    else:
        print("[WARN] 未生成最新交易日矩阵（可能没有可解析的数据）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

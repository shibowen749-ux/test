#!/usr/bin/env python3
"""抓取人民币参考汇率并输出人民币兑其他币种的一维表。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from typing import Dict, Iterable, List, Tuple

DEFAULT_URL = "https://api.frankfurter.app"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取人民币参考汇率，并输出人民币兑其他币种的一维表（CSV）。"
    )
    parser.add_argument(
        "--range",
        dest="date_range",
        help="数据区间（推荐），格式 START:END，如 2025-01-01:2025-12-31",
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
    parser.add_argument("--timeout", type=float, default=8.0, help="单次HTTP请求超时秒数（默认8秒）")
    parser.add_argument(
        "--symbols",
        default="",
        help="可选：指定币种列表（逗号分隔，如 USD,EUR,JPY）；为空则使用接口返回的全部币种",
    )
    parser.add_argument("--sleep", type=float, default=0.0, help="逐日回退抓取时请求间隔秒数")
    parser.add_argument(
        "--output",
        default="rmb_rates.csv",
        help="输出CSV文件路径（列：date,from_currency,to_currency,rate）",
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


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def http_get_json(url: str, params: Dict[str, str], timeout: float) -> dict:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RMBFxCrawler/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def normalize_cny_to_targets(rates: object) -> Dict[str, float]:
    """将接口返回归一化为: 1 CNY = x TARGET。"""
    normalized: Dict[str, float] = {}
    if not isinstance(rates, dict):
        return normalized

    for ccy, val in rates.items():
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        if v <= 0:
            continue
        normalized[str(ccy).upper()] = v
    return normalized


def fetch_range_rates(
    base_url: str,
    start: dt.date,
    end: dt.date,
    symbols: List[str],
    timeout: float,
) -> Dict[str, Dict[str, float]]:
    """优先使用区间接口一次性抓取，返回 date -> {TARGET: rate(CNY->TARGET)}。"""
    symbols_q = ",".join(symbols) if symbols else ""
    day_to_rates: Dict[str, Dict[str, float]] = {}

    url = f"{base_url.rstrip('/')}/{start:%Y-%m-%d}..{end:%Y-%m-%d}"
    params = {"from": "CNY"}
    if symbols_q:
        params["to"] = symbols_q

    payload = http_get_json(url, params, timeout=timeout)
    rates_by_day = payload.get("rates", {}) if isinstance(payload, dict) else {}
    if not isinstance(rates_by_day, dict):
        return {}

    for day, rates in rates_by_day.items():
        normalized = normalize_cny_to_targets(rates)
        if normalized:
            day_to_rates[str(day)] = normalized
    return day_to_rates


def fetch_daily_rates(
    base_url: str,
    start: dt.date,
    end: dt.date,
    symbols: List[str],
    sleep_s: float,
    timeout: float,
) -> Dict[str, Dict[str, float]]:
    day_to_rates: Dict[str, Dict[str, float]] = {}
    symbols_q = ",".join(symbols) if symbols else ""

    for d in daterange(start, end):
        day = d.strftime("%Y-%m-%d")
        url = f"{base_url.rstrip('/')}/{day}"
        params = {"from": "CNY"}
        if symbols_q:
            params["to"] = symbols_q

        try:
            payload = http_get_json(url, params, timeout=timeout)
            normalized = normalize_cny_to_targets(payload.get("rates", {}))
            if normalized:
                day_to_rates[day] = normalized
        except Exception as exc:
            print(f"[WARN] {day} 抓取失败: {exc}", file=sys.stderr)

        time.sleep(max(sleep_s, 0.0))

    return day_to_rates


def build_rmb_rows(day_to_rates: Dict[str, Dict[str, float]]) -> List[Tuple[str, str, str, float]]:
    rows: List[Tuple[str, str, str, float]] = []
    for day in sorted(day_to_rates.keys()):
        rates = day_to_rates[day]
        for ccy in sorted(rates.keys()):
            rows.append((day, "CNY", ccy, rates[ccy]))
    return rows


def write_rmb_csv(path: str, rows: List[Tuple[str, str, str, float]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "from_currency", "to_currency", "rate"])
        for date, src, dst, rate in rows:
            w.writerow([date, src, dst, f"{rate:.10f}"])


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

    print(f"抓取区间: {start} ~ {end}")
    try:
        day_to_rates = fetch_range_rates(args.url, start, end, symbols, timeout=args.timeout)
        print(f"已使用区间接口一次性抓取，共 {len(day_to_rates)} 天数据")
    except Exception as exc:
        print(f"[WARN] 区间接口抓取失败，回退逐日抓取: {exc}", file=sys.stderr)
        day_to_rates = fetch_daily_rates(
            args.url,
            start,
            end,
            symbols,
            args.sleep,
            timeout=args.timeout,
        )

    rows = build_rmb_rows(day_to_rates)
    write_rmb_csv(args.output, rows)
    print(f"已写出人民币一维汇率表: {args.output} ({len(rows)} 行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

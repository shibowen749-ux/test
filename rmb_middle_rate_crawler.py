#!/usr/bin/env python3
"""抓取 SAFE 人民币汇率中间价并输出人民币兑其他币种的一维表。"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import http.cookiejar
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

SOURCE_PAGE_URL = "https://www.safe.gov.cn/safe/rmbhlzjj/index.html"
DEFAULT_QUERY_URL = "https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do"

# SAFE 页面币别（覆盖当前页面全部币别）
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
NON_TEXT_RE = re.compile(r"[^\u4e00-\u9fa5A-Za-z]")


def _load_tk():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root, simpledialog, filedialog, messagebox
    except Exception:
        return None, None, None, None


def default_output_path() -> str:
    """默认输出到“我的文档”路径。"""
    home = Path.home()
    candidates = []
    if os.name == "nt":
        userprofile = os.environ.get("USERPROFILE")
        onedrive = os.environ.get("OneDrive")
        if userprofile:
            candidates.append(Path(userprofile) / "Documents")
        if onedrive:
            candidates.append(Path(onedrive) / "Documents")
    candidates.append(home / "Documents")
    for p in candidates:
        if p.exists() and p.is_dir():
            return str(p / "rmb_rates.csv")
    return str(home / "Documents" / "rmb_rates.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 SAFE 人民币汇率中间价，输出一维 CSV。")
    parser.add_argument("--url", default=DEFAULT_QUERY_URL, help="SAFE 查询接口地址")
    parser.add_argument("--timeout", type=float, default=15.0, help="单次请求超时秒数")
    parser.add_argument("--sleep", type=float, default=0.0, help="分段抓取间隔秒数")
    parser.add_argument(
        "--symbols",
        default="",
        help="币种代码列表，如 USD,EUR；默认空表示抓取 SAFE 源内全部币别",
    )
    parser.add_argument("--output", default="", help="输出 CSV 路径；为空时将弹窗选择保存位置")
    parser.add_argument("--start-date", default="", help="可选：开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="可选：结束日期 YYYY-MM-DD")
    return parser.parse_args()


def parse_date(date_str: str) -> dt.date:
    return dt.datetime.strptime(date_str, "%Y-%m-%d").date()


def prompt_date_window_cli() -> Tuple[dt.date, dt.date]:
    while True:
        try:
            start_s = input("请输入起始日期(YYYY-MM-DD): ").strip()
            end_s = input("请输入终止日期(YYYY-MM-DD): ").strip()
            start = parse_date(start_s)
            end = parse_date(end_s)
            if start > end:
                print("[ERROR] 起始日期不能晚于终止日期，请重新输入。", file=sys.stderr)
                continue
            return start, end
        except ValueError:
            print("[ERROR] 日期格式错误，请按 YYYY-MM-DD 重新输入。", file=sys.stderr)


def prompt_date_window_gui() -> Tuple[dt.date, dt.date] | None:
    root, simpledialog, _, messagebox = _load_tk()
    if not root:
        return None
    try:
        start_s = simpledialog.askstring("人民币汇率抓取", "请输入起始日期(YYYY-MM-DD):", parent=root)
        if not start_s:
            return None
        end_s = simpledialog.askstring("人民币汇率抓取", "请输入终止日期(YYYY-MM-DD):", parent=root)
        if not end_s:
            return None

        start = parse_date(start_s.strip())
        end = parse_date(end_s.strip())
        if start > end:
            if messagebox:
                messagebox.showerror("日期错误", "起始日期不能晚于终止日期。")
            return None
        return start, end
    except Exception as exc:
        if messagebox:
            messagebox.showerror("输入错误", f"日期输入无效：{exc}")
        return None
    finally:
        root.destroy()


def resolve_date_window(args: argparse.Namespace) -> Tuple[dt.date, dt.date]:
    if args.start_date and args.end_date:
        start = parse_date(args.start_date)
        end = parse_date(args.end_date)
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        return start, end

    picked = prompt_date_window_gui()
    if picked:
        return picked
    return prompt_date_window_cli()


def resolve_output_path(args: argparse.Namespace) -> str:
    if args.output:
        return args.output

    default_path = default_output_path()
    root, _, filedialog, _ = _load_tk()
    if root and filedialog:
        try:
            chosen = filedialog.asksaveasfilename(
                parent=root,
                title="选择汇率输出文件位置",
                defaultextension=".csv",
                initialfile="rmb_rates.csv",
                initialdir=str(Path(default_path).parent),
                filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
            )
            if chosen:
                return chosen
        finally:
            root.destroy()

    # 回退：无 GUI 时默认“我的文档”
    return default_path


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


def normalize_header_name(name: str) -> str:
    return NON_TEXT_RE.sub("", name)


def create_safe_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def warmup_safe_query(opener: urllib.request.OpenerDirector, timeout: float, query_url: str) -> None:
    req_page = urllib.request.Request(
        SOURCE_PAGE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RMBFxCrawler/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with opener.open(req_page, timeout=timeout):
        pass

    req_query = urllib.request.Request(
        query_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RMBFxCrawler/1.0)",
            "Referer": SOURCE_PAGE_URL,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with opener.open(req_query, timeout=timeout):
        pass


def http_post_html(opener: urllib.request.OpenerDirector, url: str, payload: Dict[str, str], timeout: float) -> str:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RMBFxCrawler/1.0)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": SOURCE_PAGE_URL,
            "Origin": "https://www.safe.gov.cn",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with opener.open(req, timeout=timeout) as resp:
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
        normalized_cells = [normalize_header_name(x) for x in cells]
        if "日期" in normalized_cells and any(name in CURRENCY_NAME_TO_CODE for name in normalized_cells):
            headers = normalized_cells
            continue
        if not headers:
            continue

        day = cells[0]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
            continue

        daily: Dict[str, float] = {}
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
        if daily:
            out[day] = daily
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

    opener = create_safe_opener()
    try:
        warmup_safe_query(opener, timeout=timeout, query_url=url)
    except Exception as exc:
        print(f"[WARN] 初始化查询会话失败，将直接尝试抓取: {exc}", file=sys.stderr)

    merged: Dict[str, Dict[str, float]] = {}
    for idx, (seg_start, seg_end) in enumerate(chunks, start=1):
        payload = {
            "startDate": seg_start.strftime("%Y-%m-%d"),
            "endDate": seg_end.strftime("%Y-%m-%d"),
            "queryYN": "true",
        }
        try:
            html_text = http_post_html(opener, url, payload, timeout=timeout)
            piece = parse_safe_table(html_text, symbols)
            merged.update(piece)
            if piece:
                print(f"[INFO] 分段 {idx}/{len(chunks)}: {seg_start} ~ {seg_end}, 获取 {len(piece)} 个交易日")
            else:
                print(
                    f"[WARN] 分段 {idx}/{len(chunks)}: {seg_start} ~ {seg_end} 未返回数据，"
                    "可能是该日期区间无交易日数据或所选币种无匹配。",
                    file=sys.stderr,
                )
        except Exception as exc:
            print(f"[WARN] 分段 {seg_start} ~ {seg_end} 抓取失败，尝试重建会话后重试: {exc}", file=sys.stderr)
            try:
                opener = create_safe_opener()
                warmup_safe_query(opener, timeout=timeout, query_url=url)
                html_text = http_post_html(opener, url, payload, timeout=timeout)
                piece = parse_safe_table(html_text, symbols)
                merged.update(piece)
                if piece:
                    print(
                        f"[INFO] 分段 {idx}/{len(chunks)}: {seg_start} ~ {seg_end}, 重试成功，获取 {len(piece)} 个交易日"
                    )
                else:
                    print(
                        f"[WARN] 分段 {idx}/{len(chunks)}: {seg_start} ~ {seg_end} 重试后仍无数据。",
                        file=sys.stderr,
                    )
            except Exception as retry_exc:
                print(f"[WARN] 分段 {seg_start} ~ {seg_end} 重试失败: {retry_exc}", file=sys.stderr)
        time.sleep(max(sleep_s, 0.0))

    return merged


def build_rmb_rows(day_to_rates: Dict[str, Dict[str, float]]) -> List[Tuple[str, str, str, float]]:
    rows: List[Tuple[str, str, str, float]] = []
    for day in sorted(day_to_rates.keys()):
        for ccy in sorted(day_to_rates[day].keys()):
            rows.append((day, "CNY", ccy, day_to_rates[day][ccy]))
    return rows


def write_rmb_csv(path: str, rows: List[Tuple[str, str, str, float]]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["date", "from_currency", "to_currency", "rate"])
        for day, src, dst, rate in rows:
            w.writerow([day, src, dst, f"{rate:.10f}"])


def notify_gui(title: str, message: str, is_error: bool = False) -> None:
    root, _, _, messagebox = _load_tk()
    if not root or not messagebox:
        return
    try:
        if is_error:
            messagebox.showerror(title, message, parent=root)
        else:
            messagebox.showinfo(title, message, parent=root)
    finally:
        root.destroy()


def main() -> int:
    args = parse_args()
    try:
        start, end = resolve_date_window(args)
    except ValueError as exc:
        msg = f"[ERROR] {exc}"
        print(msg, file=sys.stderr)
        notify_gui("参数错误", str(exc), is_error=True)
        return 1

    output_path = resolve_output_path(args)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print(f"数据源页面: {SOURCE_PAGE_URL}")
    print(f"抓取区间: {start} ~ {end}")
    if not symbols:
        print("[INFO] 未指定 --symbols，默认抓取 SAFE 源中的全部币别。")

    day_to_rates = fetch_rates_with_auto_chunk(
        url=args.url,
        start=start,
        end=end,
        symbols=symbols,
        timeout=args.timeout,
        sleep_s=args.sleep,
    )

    if not day_to_rates:
        err = (
            "未抓取到任何数据。请检查：\n"
            "1) 输入日期是否为交易日区间；\n"
            "2) 币种筛选是否过窄（可先不传 --symbols）；\n"
            "3) 网络是否可访问 SAFE 站点。"
        )
        print(f"[ERROR] {err}", file=sys.stderr)
        notify_gui("抓取失败", err, is_error=True)
        return 2

    rows = build_rmb_rows(day_to_rates)
    write_rmb_csv(output_path, rows)
    msg = f"已写出人民币一维汇率表: {output_path} ({len(rows)} 行)"
    print(msg)
    notify_gui("抓取完成", msg, is_error=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# 人民币汇率爬虫（已更换数据源）

该项目提供脚本 `rmb_middle_rate_crawler.py`，用于抓取近 1 年每日人民币参考汇率，并输出币种间换算汇率。

> 说明：原 `chinamoney` 源在部分环境会出现 403，本版本已切换到 `Frankfurter API`（免费、无需鉴权、稳定可用）。

## 功能

- 按日期区间抓取人民币参考汇率（默认：今天往前 365 天）。
- 产出原始汇率数据（`1 CNY = x 目标币种`）。
- 基于 CNY 枢轴，换算各币种两两汇率。
- 输出最新交易日的二维矩阵表格（行列均为币种）。

## 运行方式

```bash
python3 rmb_middle_rate_crawler.py
```

可选参数示例：

```bash
python3 rmb_middle_rate_crawler.py \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --symbols USD,EUR,JPY,HKD,GBP \
  --output cross_rates.csv \
  --latest-matrix-output latest_matrix.csv \
  --raw-output raw_middle_rates.csv
```

## 输出文件

- `raw_middle_rates.csv`：原始参考汇率，列为 `date,base_currency,currency,rate`
- `cross_rates.csv`：换算汇率，列为 `date,from_currency,to_currency,rate`
- `latest_matrix.csv`：最新交易日二维矩阵（首行为日期 + 列币种，首列为行币种）

## 数据源

- 默认源：`https://api.frankfurter.app`
- 请求方式：`/{date}?from=CNY&to=...`
- 可通过 `--url` 覆盖为兼容接口

## 说明

- 脚本按天请求，遇到个别日期失败会输出警告并继续。
- 若不指定 `--symbols`，默认使用接口返回的全部可用币种。

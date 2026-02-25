# 人民币中间价爬虫

该项目提供脚本 `rmb_middle_rate_crawler.py`，用于抓取近 1 年每日人民币中间价（默认来源：`chinamoney` 接口），并输出币种间换算汇率。

## 功能

- 按日期区间抓取人民币中间价（默认：今天往前 365 天）。
- 产出原始中间价数据。
- 根据中间价自动换算各币种两两汇率。
- 输出最新交易日的二维矩阵表格（行列均为币种）。

## 运行方式

```bash
python3 rmb_middle_rate_crawler.py
```

可选参数：

```bash
python3 rmb_middle_rate_crawler.py \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --output cross_rates.csv \
  --latest-matrix-output latest_matrix.csv \
  --raw-output raw_middle_rates.csv
```

## 输出文件

- `raw_middle_rates.csv`：原始中间价，列为 `date,pair,value`
- `cross_rates.csv`：换算汇率，列为 `date,from_currency,to_currency,rate`
- `latest_matrix.csv`：最新交易日二维矩阵（首行为日期 + 列币种，首列为行币种）

## 说明

- 脚本按天请求，遇到个别日期失败会输出警告并继续。
- 换算逻辑基于同一日期下“币种兑人民币”价格推导两两汇率。
- 若接口字段变化，脚本提供了常见字段兼容提取策略。

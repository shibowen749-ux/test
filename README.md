# 人民币汇率爬虫（一维表输出）

该项目提供脚本 `rmb_middle_rate_crawler.py`，用于抓取人民币参考汇率，并输出“人民币兑其他币种”的一维表。

## 输出格式（已调整）

输出文件默认为 `rmb_rates.csv`，列为：

- `date`
- `from_currency`（固定为 `CNY`）
- `to_currency`
- `rate`（表示 `1 CNY = rate to_currency`）

## 运行方式

### 1) 推荐：直接指定数据区间

```bash
python3 rmb_middle_rate_crawler.py --range 2025-01-01:2025-12-31
```

### 2) 兼容：使用开始/结束日期

```bash
python3 rmb_middle_rate_crawler.py --start-date 2025-01-01 --end-date 2025-12-31
```

### 3) 不指定区间：按回溯天数

```bash
python3 rmb_middle_rate_crawler.py --days 180
```

### 带币种筛选示例

```bash
python3 rmb_middle_rate_crawler.py \
  --range 2025-01-01:2025-12-31 \
  --symbols USD,EUR,JPY,HKD,GBP \
  --timeout 8 \
  --output rmb_rates.csv
```

## 数据源

- 默认源：`https://api.frankfurter.app`
- 请求方式：`/{date}?from=CNY&to=...`
- 优先尝试区间接口：`/START..END?from=CNY&to=...`
- 区间接口失败时自动回退逐日抓取

## 说明

- 脚本会输出人民币兑各币种汇率的一维表，不再输出币种两两换算矩阵。
- 若不指定 `--symbols`，默认使用接口返回的全部可用币种。

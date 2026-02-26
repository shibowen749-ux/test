# 人民币汇率爬虫（一维表输出）

该项目提供脚本 `rmb_middle_rate_crawler.py`，用于抓取 SAFE 人民币汇率中间价，并输出“人民币兑其他币种”的一维表。

## 数据源

- 来源页面：`https://www.safe.gov.cn/safe/rmbhlzjj/index.html`
- 实际查询接口：`https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do`
- 统一输出口径：`1 CNY = rate TARGET`

## 日期输入方式（前台提示输入）

运行脚本后，会在前台提示输入：

- 起始日期：`YYYY-MM-DD`
- 终止日期：`YYYY-MM-DD`

当起始日期与终止日期相差 **大于 3 个月** 时，脚本会自动分段抓取并拼接。

## 运行示例

```bash
python3 rmb_middle_rate_crawler.py --symbols USD,EUR,JPY --output rmb_rates.csv
```

随后按提示输入：

```text
请输入起始日期(YYYY-MM-DD): 2025-01-01
请输入终止日期(YYYY-MM-DD): 2025-06-30
```

## 输出格式

输出文件默认为 `rmb_rates.csv`，列为：

- `date`
- `from_currency`（固定为 `CNY`）
- `to_currency`
- `rate`（表示 `1 CNY = rate to_currency`）

## 打包 EXE

```bash
python3 -m pip install pyinstaller
python3 -m PyInstaller --clean --noconfirm --onefile --name rmb_middle_rate_crawler.exe rmb_middle_rate_crawler.py
```

产物路径：`dist/rmb_middle_rate_crawler.exe`

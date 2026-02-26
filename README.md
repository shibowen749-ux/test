# 人民币汇率爬虫（一维表输出）

该项目提供脚本 `rmb_middle_rate_crawler.py`，用于抓取 SAFE 人民币汇率中间价，并输出“人民币兑其他币种”的一维表。

## 数据源

- 来源页面：`https://www.safe.gov.cn/safe/rmbhlzjj/index.html`
- 实际查询接口：`https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do`
- 统一输出口径：`1 CNY = rate TARGET`

## 运行方式（Windows 下可直接双击 .py）

- 双击 `rmb_middle_rate_crawler.py` 后会弹窗输入：
  - 起始日期（YYYY-MM-DD）
  - 终止日期（YYYY-MM-DD）
- 之后会再弹出“保存文件”窗口，让你选择输出文件存放位置。
- 抓取完成/失败都会弹窗提示。
- 如果图形界面不可用，会自动回退到终端交互输入。

> 当起始日期与终止日期相差 **大于 3 个月** 时，脚本会自动分段抓取并拼接。

## 币别说明

- 默认不传 `--symbols` 时，会抓取 SAFE 源中**全部币别**。
- 若只想抓取部分币别，可选：`--symbols USD,EUR,JPY`。

## 输出位置

- 默认会弹窗选择保存位置。
- 若未弹窗（例如无 GUI 环境），回退默认路径：`我的文档/rmb_rates.csv`（`~/Documents/rmb_rates.csv`）。
- 可通过 `--output` 指定固定输出路径。

## 命令行运行示例（可选）

```bash
python3 rmb_middle_rate_crawler.py --start-date 2025-01-01 --end-date 2025-06-30
```

```bash
python3 rmb_middle_rate_crawler.py --start-date 2025-01-01 --end-date 2025-06-30 --symbols USD,EUR --output ./rmb_rates.csv
```

## 打包 EXE

```bash
python3 -m pip install pyinstaller
python3 -m PyInstaller --clean --noconfirm --onefile --name rmb_middle_rate_crawler.exe rmb_middle_rate_crawler.py
```

产物路径：`dist/rmb_middle_rate_crawler.exe`

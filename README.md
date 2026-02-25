# 人民币汇率爬虫（一维表输出）

该项目提供脚本 `rmb_middle_rate_crawler.py`，用于抓取 SAFE 人民币汇率中间价，并输出“人民币兑其他币种”的一维表。

## 数据源

- 来源页面：`https://www.safe.gov.cn/safe/rmbhlzjj/index.html`
- 实际查询接口：`https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do`
- 统一输出口径：`1 CNY = rate TARGET`

## 日期区间规则

- 支持 `--range START:END` 或 `--start-date + --end-date`。
- 未指定时可用 `--days` 回溯。
- 当起始日期与终止日期相差 **大于 3 个月** 时，脚本自动拆分分段抓取并拼接。

## 输出格式

输出文件默认为 `rmb_rates.csv`，列为：

- `date`
- `from_currency`（固定为 `CNY`）
- `to_currency`
- `rate`（表示 `1 CNY = rate to_currency`）

## 运行示例

```bash
python3 rmb_middle_rate_crawler.py --range 2025-01-01:2025-06-30 --symbols USD,EUR,JPY
```

## 打包 EXE

```bash
python3 -m pip install pyinstaller
python3 -m PyInstaller --clean --noconfirm --onefile --name rmb_middle_rate_crawler.exe rmb_middle_rate_crawler.py
```

产物路径：`dist/rmb_middle_rate_crawler.exe`

## GitHub 发布 v1.0（手工步骤）

```bash
git tag -a v1.0 -m "v1.0"
git push origin v1.0
# 可选（已安装 gh 时）:
# gh release create v1.0 dist/rmb_middle_rate_crawler.exe --title "v1.0" --notes "SAFE source + auto chunking"
```

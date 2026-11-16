# orderflow-alert

[English](README.md) | **简体中文**

基于 TradeStation 1 分钟 K 线流的只读订单流提醒，适用于 NQ / ES 期货（以及微型合约 MNQ / MES）。它从不下单、改单或撤单——登录时只申请行情权限。

功能：

- **每根 K 线的 delta**：`UpVolume − DownVolume`，即上涨跳动的成交量减下跌跳动的成交量，用 tick 规则估算主动买入减主动卖出。每根收盘的常规时段 K 线输出一行 JSON。
- **累计 delta**：从纽约时间 09:30 开始累计。
- **单印区提醒**：按 30 分钟时段构建当天的 market profile。出现单印区时发 macOS 通知。单印区的条件：一段只被一个时段触及的价格区间，宽度至少占当天波幅的 8%，且它的上方和下方都有被两个及以上时段触及的价格（双分布形态）。单印区被回补时再发一次通知。
- **实时面板**：`http://127.0.0.1:8765`（仅本机可访问），显示 K 线、delta、累计 delta、带单印区的 30 分钟 profile，以及提醒记录。

在 2025-02 至 2026-11 的数据上，纽约时间 11:30 前出现的单印区，到收盘仍未被回补的比例是 42–44%；13:30 前出现的是 70–72%。

## 运行环境

- macOS（通知用 `osascript`）
- Python 3.10+，只用标准库，不依赖第三方包
- 一个带 API Key（client ID + secret）的 TradeStation 账户。每个 TradeStation API Key 都预先登记了回调地址 `http://localhost:3000`，登录流程用的就是它。

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/orderflow-login        # 一次性：输入 API Key 和 secret，然后打开 TradeStation 登录页
```

凭据保存在 `~/Library/Application Support/orderflow-alert/tradestation.json`，权限 `0600`。

## 使用

```bash
.venv/bin/orderflow-alert                      # 监看 @MNQ 和 @MES，并打开面板
.venv/bin/orderflow-alert --symbol @NQ --symbol @ES
```

| 参数 | 作用 |
|---|---|
| `--symbol SYMBOL` | 要监看的 NQ / ES / MNQ / MES 合约，可重复。默认 `@MNQ` 和 `@MES`。 |
| `--no-notify` | 只输出 JSON 行，不发 macOS 通知。 |
| `--port N` | 面板端口（默认 `8765`）；`0` 表示不开面板。 |
| `--no-browser` | 开面板但不自动在浏览器里打开。 |

## 测试

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

## 许可证

MIT，见 [LICENSE](LICENSE)。

# orderflow-alert

[English](README.md) | **简体中文**

只读的订单流提醒，适用于 NQ / ES 期货（以及微型合约 MNQ / MES），数据来自 **TradeStation** 或 **盈透（Interactive Brokers）**。它从不下单、改单或撤单：TradeStation 登录时只申请行情权限，IBKR 用只读模式连接。

功能：

- **每根 K 线的 delta**：上涨跳动的成交量减下跌跳动的成交量，用 tick 规则估算主动买入减主动卖出。每根收盘的常规时段 K 线输出一行 JSON。
- **累计 delta**：从纽约时间 09:30 开始累计。
- **单印区提醒**：按 30 分钟时段构建当天的 market profile。出现单印区时发 macOS 通知。单印区的条件：一段只被一个时段触及的价格区间，宽度至少占当天波幅的 8%，且它的上方和下方都有被两个及以上时段触及的价格（双分布形态）。单印区被回补时再发一次通知。
- **实时面板**：`http://127.0.0.1:8765`（仅本机可访问），显示 K 线、delta、累计 delta、带单印区的 30 分钟 profile，以及提醒记录。

在 2025-02 至 2026-11 的数据上，纽约时间 11:30 前出现的单印区，到收盘仍未被回补的比例是 42–44%；13:30 前出现的是 70–72%。

## 数据来源

| | TradeStation（默认） | 盈透 IBKR |
|---|---|---|
| delta 怎么来 | K 线流自带的上涨跳动量 / 下跌跳动量 | 逐笔成交，用 tick 规则判断买卖 |
| 启动前当天已走完的 K 线 | 回补，带 delta | 回补，但**不带** delta（IBKR 的历史 K 线没有买卖拆分）：profile 完整，累计 delta 从程序启动时算起 |
| 额外依赖 | 无，只用标准库 | `ib_async` |
| 连接对象 | TradeStation 的 Web API | 本机运行中的 TWS 或 IB Gateway |

两边用的是同一套 tick 规则，delta 可以直接比较。要接其他券商，只需写一个输出 `bars.Bar` 的数据源；`flow_alert` 不接触任何券商字段。

## 运行环境

- macOS（通知用 `osascript`）
- Python 3.10+
- **TradeStation**：一个带 API Key（client ID + secret）的账户。每个 TradeStation API Key 都预先登记了回调地址 `http://localhost:3000`，登录流程用的就是它。
- **IBKR**：TWS 或 IB Gateway 正在运行并开启了 API（在它的 API 设置里勾选 *Enable ActiveX and Socket Clients*），且账户订阅了 CME 期货实时行情。

## 安装

TradeStation：

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/orderflow-login        # 一次性：输入 API Key 和 secret，然后打开 TradeStation 登录页
```

凭据保存在 `~/Library/Application Support/orderflow-alert/tradestation.json`，权限 `0600`。

IBKR：

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[ibkr]'
```

## 使用

```bash
.venv/bin/orderflow-alert                      # TradeStation；监看 @MNQ 和 @MES，并打开面板
.venv/bin/orderflow-alert --symbol @NQ --symbol @ES
.venv/bin/orderflow-alert --source ibkr        # IBKR，连本机 TWS 的 7496 端口
.venv/bin/orderflow-alert --source ibkr --ib-port 4002   # IB Gateway 模拟账户
```

| 参数 | 作用 |
|---|---|
| `--symbol SYMBOL` | 要监看的 NQ / ES / MNQ / MES 合约，可重复。默认 `@MNQ` 和 `@MES`。 |
| `--no-notify` | 只输出 JSON 行，不发 macOS 通知。 |
| `--port N` | 面板端口（默认 `8765`）；`0` 表示不开面板。 |
| `--no-browser` | 开面板但不自动在浏览器里打开。 |
| `--source` | `tradestation`（默认）或 `ibkr`。 |
| `--ib-host` / `--ib-port` | TWS / IB Gateway 监听的地址。默认 `127.0.0.1:7496`（TWS 实盘）。TWS 模拟 `7497`，Gateway 实盘 `4001`，Gateway 模拟 `4002`。 |
| `--ib-client-id` | API 客户端 ID，同一个 TWS 上连的各个程序要互不相同（默认 `17`）。 |

## 测试

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q             # 不需要 TWS，也不需要 TradeStation 登录
```

## 许可证

MIT，见 [LICENSE](LICENSE)。

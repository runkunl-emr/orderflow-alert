# orderflow-alert

[English](README.md) | **简体中文**

## 1. 用途

本工具监看 [NQ](https://en.wikipedia.org/wiki/E-mini)（英文）和 [ES](https://en.wikipedia.org/wiki/E-mini_S%26P)（英文）[期货](https://zh.wikipedia.org/zh-cn/期货)的[订单流](https://zh.wikipedia.org/zh-cn/訂單流交易)，也监看[微型合约](https://en.wikipedia.org/wiki/E-mini)（英文）MNQ 和 MES。

数据来自 [TradeStation](https://en.wikipedia.org/wiki/TradeStation)（英文）或[盈透证券](https://zh.wikipedia.org/zh-cn/盈透證券)（IBKR）。

本工具不下单、不改单、不撤单。

## 2. 显示的内容

| 项目 | 含义 |
|---|---|
| delta | 一根 1 分钟 K 线里，买入[成交量](https://en.wikipedia.org/wiki/Volume_%28finance%29)（英文）减卖出成交量。 |
| 累计 delta | 从纽约时间 09:30 起，所有 delta 之和。 |
| 单印区（single prints） | 只被一个 30 分钟时段触及过的价格区间。它的上方和下方都有其他时段成交过。这种形状叫双分布（double distribution）。 |
| 单印区回补 | 价格回到了单印区里。单印区消失。 |
| MFI | [资金流量指标](https://en.wikipedia.org/wiki/Money_flow_index)（Money Flow Index，英文），5 分钟 K 线、14 根。数值 0 到 100。 |

本工具按 30 分钟时段搭建当天的 [Market Profile](https://en.wikipedia.org/wiki/Market_profile)（市场轮廓，英文），再从中找单印区。

成交价比上一笔高，算买入。成交价比上一笔低，算卖出。成交价和上一笔相同，沿用上一笔的方向。这个方法叫 tick 规则（tick rule）。

单印区出现时，本工具发一条 macOS 通知。单印区被回补时，再发一条。

MFI 出现以下情况时，本工具也发 macOS 通知：

- 跌破 20，
- 回升到 20 或以上，
- 涨破 80，
- 回落到 80 或以下。

MFI 用全部 K 线计算，包括盘前。所以常规时段第一根 K 线就有 MFI 值，并且和看盘软件上的 MFI 一致。MFI 通知只在纽约时间 09:30–16:00 收盘的 K 线上发。

说明：中英文维基百科都没有「单印」「双分布」「tick 规则」的条目。背景知识请看 Market Profile 条目。

说明：2025 年 2 月至 2026 年 11 月的数据中，纽约时间 11:30 前出现的单印区，有 42–44% 到收盘仍未回补。13:30 前出现的，这个比例是 70–72%。

## 3. 开始前的检查

确认以下各项都已具备：

- [ ] 一台 Mac。
- [ ] Python 3.10 或更新版本。
- [ ] 以下券商账户之一：
  - [ ] TradeStation，并有 API Key（client ID 和 client secret）。
  - [ ] IBKR，已订阅 [CME](https://zh.wikipedia.org/zh-cn/芝加哥商品交易所集團) 期货实时行情，并已安装 TWS 或 IB Gateway。

## 4. 安装

### 4.1 TradeStation

1. 打开「终端」。
2. 进入项目文件夹。
3. 输入 `python3 -m venv .venv`，按回车。
4. 输入 `.venv/bin/pip install -e .`，按回车。
5. 输入 `.venv/bin/orderflow-login`，按回车。
6. 输入 API Key，按回车。
7. 输入 API secret，按回车。

   结果：浏览器打开 TradeStation 登录页。

8. 登录 TradeStation。
9. 同意授权请求。

   结果：页面显示「TradeStation login received」。

说明：本工具只申请行情权限。它看不到、也改不了你的账户。

说明：凭据保存在 `~/Library/Application Support/orderflow-alert/tradestation.json`。只有你的用户能读这个文件。

### 4.2 IBKR

1. 打开「终端」。
2. 进入项目文件夹。
3. 输入 `python3 -m venv .venv`，按回车。
4. 输入 `.venv/bin/pip install -e '.[ibkr]'`，按回车。
5. 启动 TWS 或 IB Gateway。
6. 打开它的 API 设置。
7. 勾选 **Enable ActiveX and Socket Clients**。
8. 勾选 **Read-Only API**。

说明：本工具的代码里没有任何下单功能。第 8 步是额外的保护：打开 **Read-Only API** 后，TWS 会拒绝所有 API 程序的下单。

## 5. 启动

1. 用 IBKR 的话，先确认 TWS 或 IB Gateway 正在运行。
2. 在「终端」里进入项目文件夹。
3. 输入 `.venv/bin/orderflow-alert`，按回车。

   结果：第一行显示正在使用的券商。例如：`flow alert started: ibkr (auto: no TradeStation login, ib_async installed)`。

   结果：浏览器打开面板，地址是 `http://127.0.0.1:8765`。

本工具自动选择券商：

| 条件 | 使用的券商 |
|---|---|
| 做过 TradeStation 登录（第 4.1 节）。 | TradeStation |
| 没做 TradeStation 登录，但安装了 IBKR 组件（第 4.2 节）。 | IBKR |
| 两样都没做。 | 无。本工具说明如何设置券商，然后退出。 |

已经登录过 TradeStation、但这次要用 IBKR：加上 `--source ibkr`。

停止本工具：按 Control-C。

### 5.1 后台运行

1. 先完成安装（第 4 节）。
2. 输入 `./install-service.sh`，按回车。

   结果：本工具在后台运行。开机自动启动，停了会自动重启。

   结果：面板地址是 `http://127.0.0.1:8765`。日志在 `~/Library/Logs/orderflow-alert.log`。

要用其他参数，加在命令后面。例如：`./install-service.sh --symbol @NQ --symbol @ES`。

取消后台运行：输入 `./install-service.sh uninstall`，按回车。

## 6. 参数

| 参数 | 作用 | 默认值 |
|---|---|---|
| `--symbol 合约` | 指定要监看的合约。每个合约写一次。 | `@MNQ` 和 `@MES` |
| `--source 名称` | 指定券商：`auto`、`tradestation` 或 `ibkr`。 | `auto` |
| `--port 端口` | 设置面板端口。`0` 表示不开面板。 | `8765` |
| `--no-browser` | 开面板，但不自动打开浏览器。 | 关 |
| `--no-notify` | 不发 macOS 通知，只在「终端」里输出。 | 关 |
| `--mfi-minutes 分钟数` | 设置计算 MFI 用的 K 线周期。 | `5` |
| `--no-mfi` | 不发 MFI 通知。 | 关 |
| `--ib-host 地址` | 设置 TWS 或 IB Gateway 的地址。 | `127.0.0.1` |
| `--ib-port 端口` | 设置 TWS 或 IB Gateway 的端口。 | `7496` |
| `--ib-client-id 编号` | 设置 API 客户端编号。同一个 TWS 上，每个程序的编号必须不同。 | `17` |

IBKR 端口：

| 程序 | 实盘账户 | 模拟账户 |
|---|---|---|
| TWS | 7496 | 7497 |
| IB Gateway | 4001 | 4002 |

示例：

- 监看 NQ 和 ES：`.venv/bin/orderflow-alert --symbol @NQ --symbol @ES`
- 用 IB Gateway 连模拟账户：`.venv/bin/orderflow-alert --ib-port 4002`

## 7. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `tradestation.json is missing` | 没做 TradeStation 登录。 | 做第 4.1 节。 |
| `No data source set up` | 没有设置任何券商。 | 做第 4.1 节或第 4.2 节。 |
| `Connect call failed ... 7496` | TWS 或 IB Gateway 没运行、API 没开，或端口不对。 | 启动 TWS 或 IB Gateway。打开 API（第 4.2 节）。核对端口（第 6 节）。 |
| `IBKR error 354` 或 `IBKR error 10089` | IBKR 账户没有 CME 实时行情。 | 在 IBKR Client Portal 里订阅 CME 期货行情。 |
| 面板打不开，8765 端口被占用。 | 另一个程序在用 8765 端口。 | 换一个端口启动，例如 `--port 8766`。 |
| 没有通知。 | 不在交易时段，或者这些 K 线是历史数据。 | 等常规时段：周一至周五，纽约时间 09:30–16:00。 |

说明：启动时作为历史数据拿到的 K 线，不会触发通知。它们只用来搭建 profile。

说明：连接断开后，本工具每 5 秒自动重连。不需要手动重启。

## 8. 限制

- IBKR 的历史 K 线没有买卖量。所以用 IBKR 时，累计 delta 从本工具启动时开始算。要得到完整数值，在纽约时间 09:30 之前启动。
- 买卖量是按价格变化估算的，不是交易所提供的真实买卖方数据。
- 只能在 macOS 上运行，因为通知用的是 macOS 的功能。

## 9. 接入其他券商

主程序只使用 `orderflow_alert/bars.py` 里的 `Bar` 类型。

接入一家券商：

1. 写一个数据源类，输出 `Bar` 对象。
2. 把这个类加到 `orderflow_alert/flow_alert.py` 的 `make_source` 里。

可以参考 `orderflow_alert/tradestation.py` 和 `orderflow_alert/ibkr.py`。

## 10. 测试

1. 输入 `.venv/bin/pip install -e '.[dev]'`，按回车。
2. 输入 `.venv/bin/pytest -q`，按回车。

   结果：所有测试通过。

说明：测试不需要 TWS，也不需要 TradeStation 登录。

## 11. 许可证

MIT。见 [LICENSE](LICENSE)。

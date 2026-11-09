# 需求端平台 · Demand Search App

**简体中文** | [English](README.en.md)

Windows 本机浏览器应用：连续讨论需求，在方案工作区查看、修改与确认成果，再按需前往电商平台继续搜索。当前范围是本机单用户桌面使用，移动端、微信真机和公网部署暂停。

这是独立的[公开实验源码副本](https://github.com/David7583/demand-search-app-public)，原私有仓库继续保留。应用原创代码、脚本和测试采用 **AGPL-3.0-only**；原创文档及合成目录数据采用 **CC BY 4.0**，第三方材料保留原许可证。公开源码不代表已提供公网服务或生产安全认证。见[许可范围](LICENSE-STATUS.md)与[验证记录](docs/VALIDATION.md)。

## 启动与配置

已初始化的项目双击 **Start-Demand-Assistant.cmd**，打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。双击 **Stop-Demand-Assistant.cmd** 停止后台；关闭标签页不会停止服务或删除历史。

首次安装要求 Windows x86_64、CPython **3.12.7**、Node.js **24.18.0**、npm **11.16.0**。在项目根目录运行：

```powershell
./scripts/init.ps1 -Python python
npm.cmd --prefix apps/client run build:h5
./scripts/start-local.ps1
```

Python依赖位于本项目.venv，前端依赖位于自己的node_modules，不借用NCP环境。见[环境](docs/ENVIRONMENT.md)、[一键启动](docs/LOCAL-DESKTOP.md)。

首次按AI向导操作，后续从设置进入。支持OpenAI、DeepSeek、Kimi、通义千问和自定义OpenAI兼容接口：选择服务商、输入Key、获取或填写模型ID，明确同意外部处理后测试并保存；失败保留上次有效配置。

**Key只输入本地配置页，不输入聊天或Git。** Windows当前用户DPAPI保护密钥；原话和历史是本机SQLite数据，仍需保护账户、备份和导出。

## 使用流程

1. 在 **AI对话** 输入愿望或任务，不必一次补齐所有字段。启用连续AI理解并确认数据范围与费用后，后续消息才自动请求模型；也可只保存本地记录。
2. AI根据情况先给方案、探索方向或整理可执行结果；关键风险条件先核实。流式回复通过完整校验后保存为草稿。
3. 在 **方案工作区** 查看方案、假设、预算估算、步骤、来源及版本。桌面支持页面切换、宽屏并排和折叠侧栏。
4. 对旧回复点击“提出修改”引用该版本；引用随消息保存。修订创建新版本，不自动回滚或覆盖已确认内容。
5. 分别确认需求和采纳方案。估算不是报价，假设不是事实；确认需求不是购买承诺。
6. 对已确认清单生成搜索入口，打开前检查关键词。每份清单最多30项；历史可接续，未发送文字刷新前应自行保留。

界面可切换 **中文 / English**，语言与目标市场独立选择。切换界面语言不会自动翻译或改写用户原话、历史AI结果、搜索词或NCP数据，也不触发模型调用；可用所需语言直接对话。

## 电商入口

| 市场 | 官方搜索入口 |
|---|---|
| 中国 | 淘宝、京东、拼多多 |
| 美国 | Amazon US、eBay US、Walmart US |
| 国际 | Etsy |

这些是固定官方搜索页URL，**不是商品API接入**。没有抓取商品、价格、库存或自动跨平台比较，不下单。市场选择不自动翻译关键词、换汇或证明配送可用。登录、验证码、地区限制和页面变化由目标站点决定，不能保证所有网络可达。见[来源状态](docs/PROVIDER-STATUS.md)、[电商替代路径](docs/PRODUCT-SOURCES.md)。

## 模拟市场

顶部导航的 **模拟市场** 是独立入口：可直接按关键词或领域浏览，无需模型 Key。内置 **500 家虚拟商家、50 个领域、1500 项模拟商品或服务**，覆盖衣食住行、AI 小硬件、软件、专业服务及工业设备。每家提供 NCP 能力声明，详情可查看协议数据。

也可以直接在AI对话中问“目前有多少家模拟商家、多少项商品或服务？”或“覆盖哪些品类？”。模型会收到当前市场库的实际统计与中英分类概况；这不是实际商品检索或真实供应证明。首次尚未建库时，先打开一次模拟市场。

在 **方案工作区** 选择已确认的需求版本，再点击 **查询模拟市场**，按清单逐项查看候选、匹配依据、预算状态及未知条件。将候选反馈到对话只会形成待发送的修改意见，不会自动确认需求、下单或调用模型。

商家、报价、资质、库存和交付信息均为合成场景数据，**不是现实商品来源或独立商家接入证据**。市场使用独立的持久化 SQLite 数据库，重启复用，不保存用户会话或查询。仓库包含可复现目录、初始化程序及专门生成的[脱敏模拟数据库快照](data/simulated-market/README.md)；日常会话库与运行配置不上传 GitHub。详见[模拟市场使用与边界](docs/SIMULATED-MARKET.md)。

## NCP与MCP

关联协议：[NeedConcord Protocol（NCP）](https://github.com/David7583/needconcord-protocol)。两个项目的代码、历史、环境和数据独立。公开名称NCP与wire **`ODIP/0.1.3-exp.1`** 分开，应用不修改上游协议。

本应用实现经校验的私人本地intent.publish/update/withdraw表示与导出；清单细节采用应用命名空间。模拟市场另生成与校验capability.advertise及proposal.submit，提案关联选定的已确认需求。它们是单一实现内的本地模拟，没有NCP节点传输、真实商家提案/结果/回执交换或跨实现互操作证明。见[兼容范围](docs/NCP-COMPATIBILITY.md)。

**MCP仅完成可行性调查，未实现server或插件。** 未来可加薄适配层复用服务，但MCP不会自动带来电商权限或需求精度。见[NCP/MCP调查](docs/research/NCP-MCP-ASSESSMENT.md)。

## 验证与边界

```powershell
./.venv/Scripts/python.exe scripts/verify.py --stage S5 --target desktop --browser
./.venv/Scripts/python.exe scripts/smoke_launcher.py
```

自动化使用隔离合成数据和模型服务，不使用真实Key/私人会话；测试构建在.local/s2-client，不覆盖日常页面。成绩与失败项见[验证记录](docs/VALIDATION.md)；CI定义不等于远端执行成功。

此前桌面修复记录为完整/生产npm审计均0项，本轮复查单独记录。原55项/7 critical与中间14项是保留的历史，不等于当前未修复，也不能把0公告当作生产安全认证。[安全状态](docs/SECURITY-BLOCKERS.md)

精简快照不含原PRD、研发历史、内部审计、真实配置、数据库、日志、缓存和备份。仅监听回环；不能直接改监听地址开放公网。生产安全、多用户、微信真机与NCP跨实现互操作尚未验证。

发起者和初始维护者：**David7583**。开发使用AI辅助，保留第三方权利，不宣称全部材料独占版权。应用代码采用AGPL-3.0-only，原创文档采用CC BY 4.0；NCP导入资产继续使用原Apache-2.0/CC BY 4.0，范围相互区分。见[许可状态](LICENSE-STATUS.md)、[安全](SECURITY.md)、[发布边界](docs/RELEASE-CHECKLIST.md)。

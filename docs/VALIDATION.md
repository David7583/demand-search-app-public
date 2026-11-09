# 桌面验证记录

## 双语与海外入口（2026-11-05）

日期：2026-11-05。范围为 Windows 本机单用户应用及经检查的私有源码同步；不是公开开源、生产部署或第三方认证。

## 实际结果

| 检查 | 结果 | 范围 |
|---|---|---|
| Python 后端 | 340/340 通过 | 隔离合成数据；会话、版本、隐私边界、NCP 本地映射及七平台入口 |
| 前端单元测试 | 61/61 通过 | 文案覆盖、语言边界、链接编码、流式处理与原有状态逻辑 |
| Edge 桌面浏览器 | 27/27 通过 | 本机真实 HTTP / DPAPI / 持久化，模型为合成服务 |
| TypeScript、ESLint、Ruff | 通过 | 未新增依赖；Python 格式检查51文件 |
| H5 构建 | 通过 | 隔离构建，不覆盖日常使用数据 |
| Python 依赖一致性 | 通过 | pip check 无冲突 |
| npm 完整/生产依赖审计 | 均0项告警 | 本轮实际联网审计；不是永久安全保证 |

首轮浏览器为26/27：英文刷新时页面标题被 Taro 静态导航覆盖。已修复初始化/页面显示生命周期并同步导航标题缓存，保留原断言；完整复测27/27。首轮失败与最终日志均保留在本地，没有删除失败或放宽测试条件。

新增后端回归覆盖四海外平台的固定域名、单参数编码、币种/关键词原样和无商品数据声明。已有恶意输入测试同步扩展到七个平台，不允许替换主机、追加跟踪/重定向参数或进行后台抓取。

## 交互验证

中英文切换保留未发送文字、未保存需求编辑、原话、AI原始回复、已确认版本和历史引用；不增加模型调用、配置请求或会话写入。语言偏好在刷新后保留，页面标题与lang一致。只将语言偏好保存在浏览器，不保存API Key。

搜索市场与界面语言独立。中国/海外/全部筛选不改关键词或已确认版本；取消弹窗不外跳，确认后只请求打开固定官网搜索URL。自动化拦截window.open验证目的地址，不冒充真实站点可访问或商品搜索成功。

本轮匿名外站检查遇到Amazon 503、eBay 403、Walmart跳转阻断页、Etsy 403；没有绕过。来源保持not_configured，network_searched=false，offers为空。见[电商调查](research/COMMERCE-OPTIONS.md)。

## GitHub CI 可移植性修复

首次远端运行和诊断轮中，后端、类型检查、H5构建及秘密扫描均通过，前端单元60/61。唯一失败是原有globs realpath夹具：Windows云runner的TEMP目录使用8.3短路径别名，库正确返回展开后的真实路径，原测试却使用未展开路径作为期望。期望值现改为操作系统的fs.realpathSync.native，保留同步/异步的文件集合与顺序严格比较；没有修改维护包实现、放宽安全超时或影响应用功能。失败日志保留，最终远端结果以Actions对应提交为准。

## 可重复执行

在本项目独立环境中：

~~~powershell
./scripts/init.ps1 -Python python
./.venv/Scripts/python.exe scripts/verify.py --stage S5 --target desktop --browser
./.venv/Scripts/python.exe scripts/smoke_launcher.py
npm.cmd --prefix apps/client audit
npm.cmd --prefix apps/client audit --omit=dev
~~~

脚本输出日志在本机.local目录，真实数据在runtime；均不上传。合成模型由tests/fixtures提供，浏览器测试使用独立回环端口与数据库，不读取真实8000会话或调用保存的真实Key。GitHub Actions使用桌面验证流程，不部署；远端执行结果需在仓库Actions单独确认，本页不把工作流定义等同于CI已通过。

## 验证状态必须分开

- **已通过Schema验证：** 本应用所支持的NCP私人intent子集、选中向量及应用自产映射，不是完整上游符合性认证。
- **已通过本地独立进程验证：** 本应用HTTP/合成服务/持久化和桌面交互；不是NCP双节点网络互操作。
- **已通过真实/生产网络安全验证：** 否，尚未验证。
- **已通过跨实现互操作验证：** 否，尚未验证。
- **尚未验证/未实现：** MCP server、真实商品API和自动比价、海外登录后搜索结果、全服务商真实模型质量、微信真机及公网多用户。MCP只有[可行性调查](research/NCP-MCP-ASSESSMENT.md)。

AI表单精细度仍受应用字段模型、上下文与模型质量影响；通过结构和界面测试不代表理解结果永远准确。未来优先用实际失败样例改进可计算约束与证据，而不是通过虚构数据填满表单。

## 来源与私有同步

源码快照保留独立应用代码、锁定依赖、合成测试、运行说明和固定NCP资产；排除原PRD、完整研发历史、内部审计、真实配置、会话、日志、备份和运行环境。清单中的SHA-256用于对应具体文件，不对真实用户数据库计算公开摘要。

应用许可证待定；私有仓库不表示开源或公网部署。NCP仓库只通过文档/仓库主页关联，未修改其代码、wire、Git历史或环境。维护者使用David7583及GitHub no-reply署名。第三方资产继续保留各自许可和来源。

English summary: 340 backend tests, 61 frontend unit tests and 27 desktop browser tests passed. The first browser run exposed a page-title reset after switching to English and reloading; it was fixed and the complete suite passed. Model inputs are synthetic. Official shopping links do not represent product API access. Language switching preserves user data and versions without invoking AI. Production security, cross-implementation NCP interoperability, MCP tools and live product search remain unverified. Authorization covers private source synchronization only, with the application license still undecided.

## 独立模拟市场（2026-11-09）

本轮遵照有限测试要求，只验证新增功能和受影响接口，未重复运行原340项后端、61项前端或27项浏览器全套，也没有重新审计未改变的依赖。原有记录仍为历史检查点。

| 本轮实际检查 | 结果 |
|---|---|
| 后端市场专项 | 8/8通过，最终5.55秒；含500份能力Schema、50类/500家/1500项、幂等/损坏拒绝、授权/版本、提案关联、预算、会话与市场数据隔离 |
| 界面翻译专项 | 2/2通过 |
| 唯一浏览器主流程 | 1/1通过，最终5.7秒；无Key目录、分页、两领域搜索、能力JSON、两项确认需求匹配、Proposal、未保存编辑提醒、反馈及迟到响应 |
| TypeScript、ESLint、Ruff、H5构建 | 通过；未新增依赖 |
| 实际本机更新 | 8000健康、静态页、模拟目录均HTTP200；500商家/1500供应项/50类别；未读取用户会话 |

浏览器前两次失败属于测试自身：第一次未关闭首次模型配置窗而等待点击超时；第二次误把POST确认回执附带字段与GET视图整体比较。修正为关闭原有向导、比较同类型已保存视图后，同一用例通过；没有通过放宽业务断言或扩大生产超时掩盖问题。全部失败、最终结果及合成截图保留本地。测试不会访问真实模型或8000日常数据。

后端首跑7/8，测试客户端未声明回环地址，被现有访问控制拒绝；只修正夹具后8/8。随后补充泛领域词降级为“领域相关”及其断言，再运行相同8项得到最终结果；不把computer/robot等泛词当具体商品满足条件。保留Starlette TestClient的httpx弃用提示，未为了无关告警修改依赖。

新增能力范围：本地合成capability.advertise与proposal.submit通过固定Schema，提案关联选定已确认intent。不是500独立进程、真实商家接入或跨实现互操作。生产网络安全和真实商品准确性仍未验证。

本轮新增脱敏数据库快照由种子全新生成，单独检查数据库表、元数据与全部目录数据，只开放这个确切合成文件的Git/扫描例外。真实会话库与运行配置没有进入源码快照。新增导出/扫描专项2/2通过，涵盖实际提交字节的正反检查；不重复原有业务套件。运行结果及SHA见[模拟市场](SIMULATED-MARKET.md)和[数据库快照](../data/simulated-market/README.md)。

复现使用模拟市场文档中的专项命令；日志在 `.local/logs/simulated-market`。本次私有同步提交使用 `[skip ci]`，避免再触发原有整套CI；**没有宣称本次远端CI通过**。已有CI流程保持可手动按正常提交触发。

English: The focused market checks passed: eight backend tests, two translation checks, one isolated desktop browser flow, type/lint and H5 build. All 500 synthetic capabilities were schema-validated. Previous full-suite results were not rerun or claimed for this change. The downloadable database is generated from synthetic seed data, separately from daily-use storage. No real model, commerce API or production network was used. Remote full-suite CI is intentionally skipped for this bounded change.

### AI市场概况补充修复（同日）

用户实际反馈对话不知道模拟市场规模与品类。现已在普通parse和连续collaborate的共用调用入口读取独立市场库，将500商家、1500供应项、50类中英名称及各类计数作为独立应用上下文传给模型；不塞全部商品，不覆盖历史需求，不把概况当检索结果或用户证据。提示版本追加 `+market-overview/1`。

仅运行3项新增专项，3/3通过（0.87秒），Ruff通过。合成Provider捕获验证两种调用收到真实目录聚合，动态样本证明非写死500/1500；缺失或损坏时数量null且继续模型调用，不建库或覆盖。没有使用真实Key或重复浏览器/旧测试。日志：`.local/logs/simulated-market/ai-context-tests.txt`、`ai-context-lint.txt`。这验证了传入模型的信息与失败处理，不等于测试了所有真实模型的回答质量。

English: A follow-up fix supplies actual local market totals and all bilingual categories to both parsing and streamed conversation. Three focused synthetic-provider tests passed. Missing or corrupt catalogs remain unknown and do not block the conversation. No live model call was made.

## 公开副本（2026-11-09）

以上私有范围/许可待定属于各次验证时的历史状态。本公开副本采用用户现已确认的AGPL-3.0-only（应用代码）及CC BY4.0（原创文档和指定合成目录），第三方许可不变。应用、依赖及模拟SQLite保持此前验收字节；本轮只检查公开文件范围、摘要、敏感资料和许可证完整性，未重跑功能套件或宣称远端CI通过。原始私有历史、个人环境、Key和会话不公开。

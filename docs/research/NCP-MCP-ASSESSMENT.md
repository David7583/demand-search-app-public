# NCP 使用范围与 MCP 适配可行性调查

调查日期：2026-11-05（Asia/Shanghai）。这是当前代码审阅和官方资料调查，**不是已完成的 MCP 接入或新的互操作测试结果**。本次未读取私人数据库、模型凭据或真实会话，未调用真实模型，也未修改 NCP 工程。

## 结论

当前应用对 NCP 的使用属于**经过校验的本地需求生命周期子集**，不是全面使用。应用能够改造成向其他 AI 客户端提供工具的 MCP server；推荐增加独立薄适配层，保留现有浏览器界面、业务服务、存储和 NCP wire。MCP 并不会带来电商访问权限，也不能自动改善需求理解准确率。

需求表单不够精细，不能全部归因于缺少商品 API。商品 API 主要影响真实候选、价格、库存、交付和商品匹配；需求表达细度还取决于本应用的数据结构、上下文、提问策略、模型能力、证据约束和评估样本。

## 当前 NCP 使用到什么程度

| 能力 | 当前实际情况 | 可核查代码 |
|---|---|---|
| 固定 Schema 与 wire | 保持 `ODIP/0.1.3-exp.1`；离线 Draft 2020-12、UUID/UTC 时间和 Schema 字节完整性校验 | [ncp_adapter.py](../../apps/server/src/demand_search/ncp_adapter.py) 的 `_validator`、`validate_schema` |
| 需求生命周期 | 仅 `intent.publish`、`intent.update`、`intent.withdraw`；只有明确确认后生成，修订连续，撤回终态 | 同文件 `SUPPORTED`、`_apply`；[demand_service.py](../../apps/server/src/demand_search/demand_service.py) 的 `confirm`、`withdraw` |
| 原话与来源 | 原话保留，已确认总预算才映射核心预算；每条来源、证据、清单细节保存在应用自定义命名空间 | `map_intent`，`constraints.specifications.demand_search_app_v1` |
| 隐私与导出 | 固定 private、不允许聚合分析；只在本地存储并经用户确认导出；不发送 NCP 网络 | `_single`；`DemandService.export` |
| 硬约束与多物品 | 已支持，但其详细语义是应用约定，其他 NCP 实现不能仅因 Schema 通过就自动理解 | [现有兼容范围](../NCP-COMPATIBILITY.md) |
| 方案交换 | 界面已有 collaboration/options，但未映射为 `proposal.submit`；它们仍是应用方案版本 | `map_intent` 未导出 collaboration；[collaboration.py](../../apps/server/src/demand_search/collaboration.py) |
| 其余协议能力 | 能力发布、提案/结果/回执交换、商业扩展、对端身份认证、网络收发/重试/outbox 未实现 | SUPPORTED 白名单明确限制；不能继承上游网络测试结果 |
| 跨实现证明 | 没有完整上游符合性运行或独立对端联调证据 | [导入说明](../../vendor/ncp/README.md) |

固定上游来自 [NeedConcord Protocol](https://github.com/David7583/needconcord-protocol)，导入摘要见 [ncp-import-lock.json](../../config/ncp-import-lock.json)。本应用独立实现适配逻辑；不是直接把整个协议参考实现嵌入应用。

### 为什么表单仍显得粗

当前 [DemandData/ShoppingItem/Fact](../../apps/server/src/demand_search/demand_models.py) 采用通用目标、必须满足/偏好文本、未知项、预算与数量，没有领域化的属性类型、测量单位规范、范围比较器、条件间依赖或逐项权重模型。文本可以描述“宽度小于80厘米”，但还不是可计算的 `width <= 80 cm` 条件。

上游 intent Schema 已有 `constraints.region`、`quantity`、`deadline`；应用目前没有逐项独立字段和明确核心映射。逐物品数量在应用清单注解里，不能随意混成整个需求的核心 quantity。方案估算及步骤同样主要是说明性结构，不是商品事实或可自动执行任务。

[ai_demand.py](../../apps/server/src/demand_search/ai_demand.py) 明确采用有限上下文：至多6条近期用户原话/6000字符、当前草稿、确认版、显式引用的历史方案，完整载荷最多32000字符。因此“有历史保存”不等于模型每次读取全部历史。现有真实性检查、结构校验能挡住部分错误，不能证明模型理解在语义上完全正确。

建议的后续细化顺序（本次调查不扩张实现范围）：

1. 用实际失败样例建立“原话 → 原子条件 → 来源/确认 → 可行动方案”的评估集，区分漏项、错项、过推断和展示不足。
2. 在应用层逐步引入可选的带类型属性、单位、范围、期限/地区和冲突说明；缺失项保持未知，避免重新变成强制填表。
3. 通过已有修订机制让用户看见并修改这些条件；不把临时建议自动确认为事实。
4. 只有获得合法候选数据后才做逐条件证据化匹配，并区分满足、不满足、未知。再决定哪些跨应用语义值得通过 NCP RFC 标准化。

这类改进可以独立于商品 API 和 MCP 进行；无需为增加表单字段先改 NCP 核心。

## 能否做成 MCP 插件

**可以，推荐“现有应用 + 可选 MCP server”，不是重写应用或把 NCP 改名为 MCP。** MCP server 向 host 提供工具/资源，host 负责模型和交互；MCP 本身不规定模型如何理解需求。[MCP 架构](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture)

两者分工：

- NCP：表达/交换需求及关联业务对象、保留来源与生命周期。
- MCP：让 AI host 发现和调用本应用能力，或在授权后读取某个需求版本。
- 本应用：负责对话、业务规则、版本、确认、权限以及实际数据来源。

当前已有 HTTP API 并不等于 MCP 兼容。现有 `/collaborate` 是应用自己的 NDJSON 流，不能直接当作 MCP 的 Streamable HTTP。需要实现 MCP 的版本协商/发现、工具输入输出、错误和取消机制，再进行真实客户端测试。[MCP transports](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports)

本次官方 `latest` 文档重定向到 `2026-07-28`。将来实施时须明确锁定 SDK/协议版本并检查目标 host 支持，不能只按旧教程把握手格式硬编码后宣称兼容所有客户端。

### 推荐的最小范围（设计提案，尚未实现）

| 拟提供能力 | 复用位置 | 默认边界 |
|---|---|---|
| `validate_ncp_packet` | ncp_adapter | 仅校验调用方给定包；无需模型或私人数据库；明示仅本地 intent 子集 |
| `build_search_links` | product_sources 的允许列表及关键词构造 | 纯计算、仅返回官方搜索地址，不自动打开/采集网页；不是商品结果 |
| `get_selected_demand_version` | DemandService 与现有版本 | 仅用户明确分享给该 MCP 客户端的会话/版本；不得默认枚举全部私人历史 |
| `export_selected_ncp` | 原字节导出路径 | 将内容送给 host 属于新的数据披露，必须单独授权；不能将本地导出许可视为分享许可 |
| 写入草案/请求解析 | 可选后续阶段，复用现有服务和幂等键 | 明示将写入本地和/或付费模型调用；保存草案与用户确认分开 |
| 确认、撤回、删除、付费解析 | 不作为首个默认工具集 | 模型传入 `confirm:true` 不等于真实人的确认；需应用侧授权流程 |

MCP 的工具名、输入/输出 Schema、错误语义必须准确；`readOnlyHint` 等声明不是安全隔离或授权机制。[MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)

首期建议本机 **stdio**：host 启动独立子进程，标准输出只承载协议，日志写标准错误；复用本项目锁定依赖和现有服务，不复制第二套数据库/业务实现，不要求启动公网服务。[stdio 规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)

普通工具操作不必额外调用本应用已配置模型，host 自身通常已有模型。若另加“调用应用模型解析”工具，必须明确服务商、发送范围、费用、超时/取消和幂等重试；不能因为调用来自 MCP 就绕过现有同意机制。

### 实施前必须解决的权限差异

当前服务的 owner 是本机 LOCAL_OWNER，HTTP 层还提供回环/会话/CSRF 防护。MCP 直接复用业务层时不能假定这些 HTTP 保护仍然存在，也不能把“运行在同一电脑”视为全部历史的披露许可。应增加 MCP 客户端授权与会话/版本范围，默认不触碰密钥、浏览器 Cookie 或其他目录。对 stdio 要确保受信启动路径和进程权限；将来远程 HTTP 则需另做认证授权和多用户隔离。[MCP 安全指南](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices)、[授权规范](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization)

返回内容可能被 host 传给外部模型；即使 NCP 包里的 sharing_scope 仍为 private，也不能因此声称没有离开本机。第三方商品/页面文字应视为不可信数据，不允许它指示读取凭据、执行任意命令或修改确认状态。

验收应覆盖版本发现、tools/list/call、输入/输出 Schema、无权读取、异常/取消、幂等、无隐式付费/确认，并用独立客户端运行；官方 [MCP Inspector](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector) 可用于调试与自动化。通过后才能将对应范围标记为“已验证 MCP 兼容”，仍不能自动证明 NCP 跨实现互操作。

## 本次调查状态

已完成代码路径核查及官方 MCP 资料调查。没有新增 MCP 运行入口、SDK 依赖、公开服务、真实账户访问或任何兼容性认证。结论是工程上可行，推荐边界已明确；实施与验证应作为后续有明确验收范围的工作。

# S2 需求版本、确认与本地协议表示

本阶段把会话、原文消息、需求对象、不可变版本及 NCP 消息分别保存。S2.1每个会话一个可含多商品清单的需求；另一独立需求使用新会话，避免继承上个需求的条件。

## 工作流与来源

1. 用户消息先按S1流程保存。解析接口只接受本会话最新的已保存用户消息ID，不接受客户端改写原文或伪造助手消息。
2. 用户明确同意后，模型收到本次原文、当前草稿、已确认需求和最多6条近期用户消息（总6000字符），以及本条消息明确引用的一份同会话版本；不读取其他会话、不发送完整无限历史。模型返回形成新draft版本，不能自动确认。
3. 用户在卡片里检查或编辑目标、硬条件、偏好、未知、预算、准备度和替代方案。确认动作创建另一个confirmed版本；旧draft和旧confirmed均保留。替代方案必须明确选择true/false；unknown不会自动变成已知事实。
4. 再次修改预算，例如1500改3000，生成新版本且记录parent_version_id。没有覆盖原文、旧预算或旧时间。AI解析失败时，已确认指针不变。
5. 模型提示可能是新需求时，用户必须明确选择继续当前需求，或新建会话。不能由模型自动替换当前需求。
6. 撤回仅作用于本地需求与本地NCP序列，属终态。不能复活，也不取消站外订单；删除私人会话是另一操作。

字段source保留来源声明；confirmed记录用户是否确认。用户确认一条模型推断后仍保留model_inferred来源并标confirmed=true；手工新增或修改字段使用user_confirmed，原来源在旧版本可追溯。source=unknown不会仅因整卡确认变成事实。整卡user_confirmed不是购买承诺、第三方事实认证、共享或聚合授权。

每个版本保存source_message_id、original_text、parent_version_id、模型/服务商及prompt_version。版本号与NCP revision分开：AI草稿不消费NCP revision，首个确认生成publish，随后确认生成连续update，撤回生成withdraw。

## 一致性与失败恢复

写操作使用SQLite事务和乐观版本检查。AI网络请求期间不持有数据库写锁；返回后重新核对当前版本、来源消息和最新消息序号。解析期间若新增消息、确认版本或删除会话，迟到结果拒绝，不覆盖较新状态。确认旧卡片时若存在尚未解析的新消息，也会拒绝。

request_id是独立UUID，按会话/操作/请求内容摘要绑定。成功请求重试返回既有结果，不再生成版本或付费调用；同ID不同内容拒绝。正在执行的同ID请求返回REQUEST_IN_PROGRESS。持久化租约120秒；进程崩溃后可等租约过期使用同ID恢复，普通失败可重试。

这不保证外部付费调用exactly-once：外部服务返回与本地提交之间崩溃可能需要再次调用。界面不得无提示自动重试付费请求。每会话最多100个版本和1000个需求写请求，达到上限应导出并新建会话。

## API 合同

base为 `/api/v1/conversations/{conversation_id}/demand`，所有接口复用本地Cookie/CSRF及同源限制。

| 操作 | 请求 |
|---|---|
| GET base | 读取需求、版本列表、current_version、confirmed_version；没有模型调用 |
| POST /parse | message_id、expected_version_id（首次null）、request_id、consent、可选config_id |
| POST /confirm | version_id、request_id、confirm:true、continue_current_intent、完整edits |
| POST /withdraw | expected_version_id、request_id、confirm:true、reason |
| POST /export | acknowledge_private_export:true |

写接口返回读取视图及result_version_id、duplicate。主要冲突码：DEMAND_VERSION_CONFLICT、STALE_MESSAGE、STALE_ANALYSIS、REQUEST_ID_CONFLICT、REQUEST_IN_PROGRESS、DEMAND_WITHDRAWN、INTENT_CLARIFICATION_REQUIRED。输入或模型结构错误不会改变已确认版本。

edits含desired_outcome、required/preferred/unknown字符串数组、budget_ceiling（null或amount/currency）、readiness和alternatives_acceptable。客户端无法直接设置source、confirmed、原文、模型名或NCP消息ID；这些由服务端结合旧版和实际确认动作记录。

## 私人导出与删除

confirmed版本才创建私人的NCP本地表示。每个需求使用匿名本地sender，privacy固定private及allow_aggregate_analytics=false；不向网络发送，没有回执或已投递声明。NCP消息使用上游实际wire `ODIP/0.1.3-exp.1`，校验原始Schema及适配器支持的状态约束。

数据库保存每条消息的确切UTF-8字节；重复导出不刷新时间戳、消息ID或重新序列化。导出同时含packet对象、packet_utf8原始文本和SHA-256。用户必须明确确认私人导出，下载后由用户自行保管。具体支持范围见[NCP边界](NCP-COMPATIBILITY.md)。

S1通用会话导出升级为 `demand-search.conversations.export/2`，加入demands、versions与packet_utf8；不包含模型配置或密钥。删除单个/全部会话通过外键级联删除相关需求、版本、请求和本地协议包；不操作模型凭据或外部服务商的数据。

## 验证范围

独立测试仅用合成模型和隔离runtime/test-demand-*数据，覆盖预算修订、原文保留、A/B上下文、限额、请求幂等、并发处理中拒绝、租约恢复、迟到响应、用户确认、撤回、导出和删除。另有真实子进程重开数据库，确认版本及确切协议字节不变。

这些不是全服务商真实接入、完整NCP核心符合性、独立网络互操作、跨语言验证或生产安全证明。S0/S1的55项依赖告警（含7项critical）作为历史证据保留；后续修复及当前阻断项见[安全状态](SECURITY-BLOCKERS.md)。本应用继续只作本地研发，未获公开部署授权。

## S2.1 连续对话与多商品清单

一个需求现在可表示一份购物清单，仍复用同一 demand/intent 及不可变版本链。每版新增 items（最多30条，包括已移除条目）：服务端稳定 item_id、名称、数量/单位、条目来源及证据/确认标记、各自必须/偏好/未知条件、单项预算、预算口径 unit/line_total/unknown、active/removed 状态。条目来源及 confirmed 描述名称与数量/单位这一整体声明，条件与预算继续保留独立来源，不等于商家商品事实。

顶层 budget_ceiling 表示整份清单总预算，不能自动复制为每件预算。数量或预算口径未知时保留 null/unknown，不默认为一件或单价。一次输入可整理多件商品，后续追加、修改指定项及移除条目都形成新版本；移除先成为草稿，明确检查确认后才进入确认版。模型不能生成 confirmed，也不能声明 user_confirmed。模型只能引用当前需求已有 item_id；新项使用 null，由服务端生成 UUID；未知或重复 ID 拒绝。模型漏掉的旧条目会保留，不能因模型遗漏而删除。

上下文除最近用户消息及 confirmed_demand 外，可含明确未确认的 current_draft，支持尚未确认时继续讨论，不把草稿升级为用户事实。输出上限仅此解析提升至12288 tokens；配置测试仍为4096。上下文32000字符、用户原文8000字符和协议包64 KiB上限不变；超过上限明确报错，请缩短条件或分会话，不静默截断清单。真实模型可能有更低输出额度或耗时限制，截断视为失败，旧版保留。

确认 edits.items 可携带全清单，使用 item_id 关联；编辑输入不允许伪造 source/confirmed。旧客户端省略或传 null 时保留条目及其原确认标记，不将未显示的条目自动确认。部分提交遗漏的条目也保留；删除需显式 status=removed。整卡确认不等于每项未知信息已知。

兼容读取为旧版缺失 items 提供空列表视图，但不回写数据库历史 JSON，不重建旧协议包。新版本才保存新结构。清单是应用内约定；NCP 使用相同 wire 与 intent，将 shopping_list 放入已有应用注解。一个清单撤回作用于整体需求；单项移除不表示取消站外订单。没有商品 API 接入或自动购买声明。

最新用户原文检查按 user 消息序号，助手说明不使原文过时。本阶段聊天回复可由持久化版本派生，不增加伪造用户消息或额外模型调用。tests/test_multi_items.py 覆盖20/30项、追加/修改/移除、预算范围、来源、未知/重复ID、幂等、旧JSON/确切协议字节、重开存储和超大包回滚；所有模型与商品描述均为合成数据。


## 自适应协作增量（2026-11-04）

当前电脑端默认使用 /collaborate 流式路径，原 /parse 保留向后兼容。新增可选的 assistant_reply、collaboration、solution_selection、solution_confirmed 都位于应用的版本 JSON 内，未增加数据库表或改变 NCP wire。

新协作提示版本为 demand-search-collaboration/1，要求有用的回复与可讨论成果；旧提取接口继续使用原提示版本，未伪装为新策略。临时流不进入版本链，最终结构和并发校验通过后复用原事务提交。新字段缺失的旧版只做兼容读取，不重写历史。

确认请求可明确选择本版本的 selected_option_id，并单独设置 confirm_solution。这仅表达用户采纳；假设、估算、供应商和报价事实不因此获得认证。需要关键核实的方案不能标记采纳。方案不自动进入NCP消息的已确认条件。

工作区反馈保存为正常用户原话并参与后续解析；未保存编辑先明确带回或放弃，不因切页静默丢失。详情见[自适应协作合同](ADAPTIVE-COLLABORATION.md)。以上是应用内扩展，不修改协议工程。

## 历史方案引用（2026-11-05）

保存用户原文的 POST /api/v1/conversations/{id}/messages 可选接收 reference_version_id。服务端只接受同一会话、同一需求所属版本，将其 id、number、status 写入已有消息 metadata.reference_version；原文不拼接方案全文，不新增数据库表或迁移。客户端不能直接提交任意 metadata 或伪造版本标签。

消息幂等比较同时包含正文与引用ID。同一 client_message_id 改换引用会返回 MESSAGE_ID_CONFLICT；跨会话或不存在的引用返回 REFERENCE_VERSION_NOT_FOUND。历史读取与私人导出均保留引用，刷新页面或重建服务后不会丢失。

生成时仍只接收已存 message_id；由服务端读取引用并重新检查归属，将 referenced_version={id,number,status,data} 加入模型上下文。不允许解析请求另塞引用以替换原消息关联。历史方案与助手回复不进入原话 evidence_text，引用不是采纳、预算确认或事实验证。

新草稿仍以当前 expected_version_id 为父版本，保留当前确认指针；选旧版讨论不会回滚到该版本。总上下文仍限32000字符，超限在调用模型前拒绝，不能为了塞入旧方案而截断用户条件。引用绑定后不可静默修改，若希望取消该引用，应发送不带引用的新消息。

协作提示版本为 demand-search-collaboration/2；旧同步解析带引用时使用 demand-search-s2.1/2，无引用的旧同步解析仍保持原提示版本。NCP wire、Schema、旧消息及旧版本字节均不改动。

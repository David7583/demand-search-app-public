# S2 本地 API

默认127.0.0.1:8000，仅local-dev。除静态页面、健康/能力状态和会话引导外，业务接口需内存Cookie；写请求需JSON和X-DSA-CSRF，跨源/非本机拒绝。错误不回显完整输入或Key。

| 路径 | 行为 |
|---|---|
| GET /healthz | 当前实例阶段与迁移就绪 |
| GET /api/v1/session | 本地会话及CSRF；HttpOnly/SameSite=Strict Cookie |
| GET /api/v1/status | 能力及公开部署阻断；保存配置不代表持续在线 |
| GET /api/v1/providers/status | 三家商品源均not_configured |
| /api/v1/config/* | [模型合同](AI-PROVIDERS.md) |
| /api/v1/conversations*、/api/v1/me/* | [历史合同](HISTORY.md) |
| /api/v1/conversations/{id}/demand* | [需求与版本合同](DEMANDS.md) |

需求base为 /api/v1/conversations/{id}/demand。GET返回demand、versions、current_version和confirmed_version，不调用模型。

| POST后缀 | 请求与约束 |
|---|---|
| /parse | message_id、expected_version_id（首次null）、request_id、consent:true、可选config_id；仅本会话最新已保存用户原文 |
| /confirm | version_id、request_id、confirm:true、continue_current_intent、完整edits；生成新确认版本 |
| /withdraw | expected_version_id、request_id、confirm:true、reason；终态，不复活 |
| /export | acknowledge_private_export:true；返回私人packet、确切packet_utf8及SHA-256 |

edits含目标、required/preferred/unknown字符串数组、预算、准备度和明确的alternatives_acceptable布尔值。客户端不能设置原文、模型归因、确认来源或协议消息ID。写响应额外含result_version_id及duplicate；草稿不消费NCP revision。

request_id绑定会话、操作和内容，成功重试不再次调用模型。处理中返回REQUEST_IN_PROGRESS，内容冲突返回REQUEST_ID_CONFLICT；租约恢复不保证外部计费exactly-once，不能无提示自动重试付费调用。版本/迟到冲突需刷新，不强行覆盖。

历史导出升级为demand-search.conversations.export/2，包含需求、全部版本和本地协议字节，仍排除模型配置/Key。删除通过级联处理私人关联数据，不代表共享撤回或取消订单。

输入正文限64KiB、接收限时10秒，模型调用受并发/频率限制；不是多用户认证。统一错误为 `{"error":{"code":"…","message":"…"}}`，S2主要码包括DEMAND_VERSION_CONFLICT、STALE_MESSAGE、STALE_ANALYSIS、DEMAND_WITHDRAWN和INTENT_CLARIFICATION_REQUIRED。

NCP只支持private本地意图序列，无发送、回执、商品检索、下单或支付API。

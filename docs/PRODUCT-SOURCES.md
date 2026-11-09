# 站外关键词搜索与商品来源边界

本版本**不接任何商品或联盟 API**。淘宝、京东、拼多多、Amazon US、eBay US、Walmart US、Etsy 均保持 `not_configured`，不采集价格、库存、商品详情或购物账户。AI Key 不提供电商数据权限。

## 本地搜索计划

`POST /api/v1/conversations/{conversation_id}/demand/search-plan` 接收已确认的 `version_id` 和可选 `item_ids`（1–30 个不重复 ID）。它在本机生成链接，不访问外网、不修改需求历史，也不写入商品结果。

计划绑定确切版本和项目 ID。只允许本会话已确认版本及未移除项目；旧确认版本可查看，但返回版本号、创建时间及是否最新，不能把旧条件视为最新条件。未确认名称返回 `SEARCH_ITEM_UNCONFIRMED`，未确认版本、已撤回需求及其他会话的对象均拒绝。

关键词仅使用已确认的项目名称、已确认且非 unknown 的共有/单项硬约束，以及预算口径明确的已确认单项预算。单价与该项合计预算分别标注，**整份清单总预算不会复制成每项预算**。未知、未确认预算只留提示，不伪装成价格筛选。偏好、原文、证据片段、未知项及其他会话不加入链接。预算只是普通关键词，平台未必将其执行为精确价格过滤。

旧 S2 版本没有 `items` 时，以该确认版目标兼容为一项；不会重写历史。合成查询超过 200 个 UTF-16 代码单元时返回 `SEARCH_QUERY_TOO_LONG`，要求用户精简名称/硬约束后确认新版本；不静默截断条件。该上限与浏览器字符串校验一致。

输出仍固定 `kind:external_search_plan`、`network_searched:false`、`offers:[]`；顶层与来源各有 `sourceCoverageNote`。新增英文说明、英文标签和地区元数据用于展示，不改变原需求、NCP wire 标识或已保存版本。站外链接不等于商品级搜索、自动比价、已验证匹配或成交。

## 固定链接与地区

只使用下列固定 HTTPS 目标，搜索词通过独立单一参数百分号编码。模型和请求不能提供域名、路径、重定向或任意链接。界面在打开前展示实际关键词，由用户明确选择平台；不得自动批量打开或从跳转推定购买。

| 来源 | 地区标识 | 固定模板 |
|---|---|---|
| 淘宝 | `CN` | `https://s.taobao.com/search?q=<encoded>` |
| 京东 | `CN` | `https://search.jd.com/Search?keyword=<encoded>` |
| 拼多多 | `CN` | `https://mobile.yangkeduo.com/search_result.html?search_key=<encoded>` |
| Amazon US | `US` | `https://www.amazon.com/s?k=<encoded>` |
| eBay US | `US` | `https://www.ebay.com/sch/i.html?_nkw=<encoded>` |
| Walmart US | `US` | `https://www.walmart.com/search?q=<encoded>` |
| Etsy | `GLOBAL` | `https://www.etsy.com/search?q=<encoded>` |

中英文界面均可使用全部入口。切换语言不自动翻译用户原话或搜索词，不自动换汇，不把人民币预算改作美元。美国站不代表用户必能购买或收到货；Etsy 的 GLOBAL 标识也不保证某卖家向全球配送。语言、币种、收货地点、税费和物流仍由用户在原平台检查。

本地查询词编辑仅用于用户本次出站选择，不应悄悄改变确认需求或保存历史。输入英文关键词通常更适合英语平台，但这是可选择的表达调整，不是已验证匹配提升；应用不偷偷把整段会话发给平台。

## 实际核查与错误退路

2026-11-04 中国平台匿名浏览器核查：淘宝、拼多多合成词地址返回 200，京东进入官方登录页。2026-11-05 海外模板的匿名本机请求：Amazon 503、eBay 403、Walmart 重定向阻断页（即使 HTTP 200 也不算成功）、Etsy 403；另一路网页研究能读取 Etsy 查询页。完整证据与来源见 [PROVIDER-STATUS.md](PROVIDER-STATUS.md) 和 [电商替代方案调查](research/COMMERCE-OPTIONS.md)。

HTTP 200、标题或成功打开新窗口只证明相应动作或地址响应，不能证明有效商品、当前账户权限或所有条件已被执行。目标站可能要求登录、JavaScript、验证码、所在地区或 App；应用不绕过限制。无法打开时可复制关键词或官方链接，由用户在原站继续。

微信仅保留合规复制/原平台搜索退路，尚未完成目标小程序授权或真机跳转验证，当前相关开发暂停。H5 构建与手机视口测试不能替代微信真机。

## 后续数据路径

当前不代用户注册、签约、申请接口或收集商品平台秘密。最值得优先评估的是用户主动提供候选商品的链接和规格摘录，或取得商家明确展示授权的目录/feed；两者均需保留来源、观测时间、币种、规格及未核验状态，不能将缺失字段补成真实事实。专用导入/自动比较尚未实现。

平台 API 的账号注册、应用权限、用户 OAuth 和生产审批是不同条件；“Open API”“不需要用户授权”均不自动代表无需应用凭证或无用途限制。Amazon 当前应查 Creators API，eBay 生产 Buy API 有审批与合同要求，Walmart/Etsy 也有各自准入范围。官方链接与现行核查结论集中维护于[调查报告](research/COMMERCE-OPTIONS.md)，不沿用旧教程直接宣称可接入。

如未来另行决定接商品 API，需独立审核来源授权、价格观测时间、规格证据、限流与部分失败隔离。一家合法来源只能称单源验证；同次查询至少两家合法商品级来源返回可核验结果后，才可能验收自动跨平台商品比较。未授权或失败不能写成“没有商品”，两家来源也不自动等于全市场覆盖。

本阶段无爬虫、未知来源聚合 API、站内交易或 NCP 网络发送。依赖安全以[当前安全记录](SECURITY-BLOCKERS.md)为准；旧 55/7 和中间 14 项保留在历史报告中。本轮已授权独立公开源码副本；许可见LICENSE-STATUS.md，公网部署不在授权内。

## English summary

The local search-plan endpoint accepts confirmed demand versions and selected item IDs, then constructs official keyword URLs without network searches or product retrieval. Seven fixed providers are supported. Keywords come from confirmed names, hard constraints and unambiguous item budgets; total budgets are not repeated for every item. URLs are bound to the exact version and item, and arbitrary destinations are rejected.

UI language and market metadata are presentation only. No automatic translation, exchange-rate conversion, shipping verification, price filtering or product matching is claimed. External access may be blocked or require normal user login/verification. Future product data requires explicit permission and source evidence; a private repository does not make the application publicly licensed.

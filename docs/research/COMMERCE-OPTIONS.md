# 电商接入替代路径与海外搜索入口调查

核验日期：2026-11-05（Asia/Shanghai）。这是研究与访问证据，不表示已经取得平台 API 授权，也不表示以下建议均已实现。本轮继续不接中国或海外商品 API，不读取购物账户、Cookie 或登录状态，不代用户下单。

## 结论

当前最可落地的路线是“更好的需求表达 → 用户检查搜索词 → 官方网站继续搜索 → 用户选择性提供候选商品资料 → 按已确认约束讨论差异”。其中海外官方搜索入口适合本轮增加；结构化商品资料导入与比较仍是后续候选能力，不能写成已经完成。

缺少商品 API 主要限制真实价格、库存、规格及覆盖面的获取。它不能完整解释需求表单不够细致：需求建模、提问与方案策略、领域约束和模型输出质量仍需单独改进。换成 MCP 接入方式也不会产生商品数据授权。

## 可选路线

| 路线 | 可提供的价值 | 约束与适用范围 | 本轮处理 |
|---|---|---|---|
| 官方关键词搜索页 | 无商品 API 凭证也能把明确需求带到原平台 | 不获取商品结果；预算文字不等于价格筛选；可能要求登录、验证或所在地区支持 | 增加固定海外入口 |
| 用户主动提交商品链接及短规格/价格摘录 | 对用户指定的少数候选，按硬约束逐项比较并指出缺失信息 | 链接本身不是已抓取证据；标记“用户提供、未独立核验”、采集时间、币种/规格；不自动声称现价；避免不必要的个人订单信息 | 后续优先建议；现有文字对话可讨论用户提供内容，专用导入界面未实现 |
| 商家直接提供并授权的 CSV/JSON/feed | 能获得可核对的商品字段、有效期与来源；适合从小范围开始 | 须约定展示、缓存、图片与再分发权；只覆盖合作商家；数据过期处理必需 | 找到真实授权合作方后再开发适配器 |
| 商家同意的独立站接口 | 比大型平台全量搜索更可控；可以先验证一个真实目录 | Shopify 等是逐店接口，不等于全球目录；公开可读不等于无限制采集/再发布 | 未来候选，当前未接入 |
| 官方开发者/联盟接口 | 允许时可获得结构化商品数据 | 按平台审批和条款；推广商品池必须清晰说明覆盖范围；佣金不得参与需求符合度排序 | 本轮不申请、不接入 |
| 第三方商品/搜索数据供应商 | 可能缩短接入时间 | 必须验证上游授权、可展示/缓存/再分发范围、更新频率、地区、删除与费用条款；“有 API”不是合法性或准确性证明 | 不以未知抓取代理替代授权 |

推广池存在覆盖偏差，与“排序是否按佣金加权”是两个问题。即使不把佣金纳入排序，也不能将推广池说成中立全量商品搜索。用户已要求当前版本不走此路线，故仅记录区别，不实施联盟接入。

## 海外官方搜索 URL

仅选择四个固定官网地址，查询内容单独 URL 编码，不接受模型给出的任意域名、协议或跟踪参数。国家站固定标明；切换界面语言不应悄悄改变预算币种、用户原话或站点地区。允许用户先编辑搜索词（例如英语关键词）再跳转。

| 入口 | 固定模板 | 范围 |
|---|---|---|
| Amazon US | `https://www.amazon.com/s?k={encoded_query}` | 美国站；不保证跨境配送 |
| eBay US | `https://www.ebay.com/sch/i.html?_nkw={encoded_query}` | 美国网站入口；交易与物流范围取决于商品 |
| Walmart US | `https://www.walmart.com/search?q={encoded_query}` | 美国站；地区与配送限制需原站确认 |
| Etsy | `https://www.etsy.com/search?q={encoded_query}` | 官方英文入口；地区/币种可能随原站设置变化 |

按钮应为“去原平台继续搜索 / Continue searching on platform”，而不是“查看已匹配商品”。只在用户主动点击时传递其检查过的关键词；不传送整段会话、原始需求、密钥或本地身份信息。所有来源仍为 `not_configured` 商品 API 状态，计划维持 `network_searched:false`、`offers:[]`。

### 本轮实际访问证据

2026-11-05 使用合成词 `desk lamp`，匿名 HTTPS GET，不附带 Cookie、不登录、不重试绕过限制，未采集或保存商品正文。实际请求分别为上述模板的 `desk%20lamp`。结果：

| 站点 | 本机匿名 HTTP 结果 | 解释 |
|---|---|---|
| Amazon | HTTP 503 | 目标未向该请求提供搜索结果；不能判为搜索成功 |
| eBay | HTTP 403 | 请求被拒绝；停止，不绕过 |
| Walmart | HTTP 200，但最终路径为 `/blocked` | 是阻断页，不能把 200 算成搜索页通过 |
| Etsy | HTTP 403 | 本机请求被拒绝；停止，不绕过 |

独立网页研究工具的结果略有不同：[Etsy 合成查询](https://www.etsy.com/search?q=desk+lamp)可读取搜索页；[eBay 官方同类查询](https://www.ebay.com/sch/i.html?_nkw=desk+lamp&_sop=1)有官方搜索索引结果，但直接读取失败；[Amazon 主页](https://www.amazon.com/)出现启用 JavaScript / 人机验证提示；[Walmart 主页](https://www.walmart.com/)可读而查询工具无法打开该搜索链接。不同客户端和访问路径结果不同，不外推为用户浏览器一定成功或一定失败。

因此可以验证应用构造正确链接并尝试新窗口打开，但“实际浏览器完成搜索”“登录后商品结果”“商品接口已连通”必须分别记录；本报告不证明这三项已通过。遇到原站限制，应让用户在原站正常处理或复制关键词手动搜索，应用不得代为规避限制。

## 官方接口现状（供以后决策，不是本轮接入计划）

- **eBay Browse API** 可按关键词和类别等查询商品；官方 Buy API 要求区分 Sandbox 与 Production，生产使用需满足资格、审批与相关协议，审批并无保证。不能将创建开发者账号等同于正式商品数据权限。[Browse API](https://developer.ebay.com/api-docs/buy/static/api-browse.html)、[生产要求](https://developer.ebay.com/api-docs/buy/static/buy-requirements.html)。
- **Amazon** 当前官方文档已将 PA-API 5 标为弃用，继任为 Creators API。文档列出目标市场 Associates 资格、通过 Creators API 访问 PA API 时近 30 天至少 10 笔合格销售、注册及凭证要求。它不是无门槛中立全量商品数据出口，旧 PA-API 教程不能直接沿用。[Creators API](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction)、[弃用说明](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation)。
- **Amazon SP-API** 是面向 selling partners 的另一套应用注册与授权体系，不能当作绕过 Associates 条件的消费者全量搜索接口。[应用注册](https://developer-docs.amazon/sp-api/docs/registering-your-application)。
- **Walmart Marketplace APIs** 面向获批准的卖家、合作伙伴与解决方案提供商，覆盖商品、价格、库存、订单等业务，并非任意个人获得全站购物搜索权限的承诺。[官方入门](https://developer.walmart.com/global-marketplace/docs/getting-started)。
- **Etsy Open API** 需要注册并获批应用；个人、小规模与商业用途存在不同准入路径，实际使用需符合所批准用途及 API 条款。“Open API”不等于匿名任意调用。[官方帮助](https://help.etsy.com/hc/en-us/articles/360025870013-How-to-Use-Etsy-s-API)、[请求认证要求](https://developers.etsy.com/documentation/essentials/requests/)。
- **Shopify Storefront API** 支持逐店商品/集合/搜索等能力，部分查询可无 token，其他能力需要 token。适合作为取得商家合作后的小范围目录来源；不应把 tokenless 功能解释为任意跨店采集、内容再授权或全量市场搜索许可。[官方 API](https://shopify.dev/docs/api/storefront/latest)。

## 建议优先级

1. 本轮完成双语 UI 与上述官方入口，明确外跳限制，保持零商品 API 可运行。
2. 下一轮优先改进领域约束与候选商品资料整理：把“信息缺失”“明确不符合”“用户提供但未核验”分开，不用虚构匹配分数填满表格。
3. 如果用户确有商家合作或已批数据权限，再以独立适配器验证小规模真实商品来源。覆盖两家也不自动证明全量覆盖、价格实时或跨平台同款匹配准确。

## English summary

This investigation recommends official search-page handoffs now and user-supplied candidate details or explicitly licensed merchant feeds later. No product API integration is claimed. Amazon US, eBay US, Walmart US and Etsy search templates use fixed HTTPS hosts and encoded keywords. Anonymous local checks encountered 503, 403, a Walmart block-page redirect and 403 respectively; these are not successful product-search validations. A separate research fetch could read Etsy, illustrating client-dependent access. Never bypass login, verification or access restrictions.

API registration is not production authorization. eBay, Amazon, Walmart and Etsy each have eligibility, authentication or review requirements. Amazon's current successor to PA-API 5 is Creators API. A merchant-specific Shopify integration is an alternative only within its permitted scope. Switching UI language must not silently translate user evidence, convert budgets or imply live product data. MCP changes tool access, not commerce authorization.

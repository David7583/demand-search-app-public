# 商品来源与外部跳转状态

更新日期：2026-11-05（Asia/Shanghai）。本版本没有接入任何商品或联盟 API；只提供基于已确认需求的官方关键词搜索入口。站外入口不等于商品聚合、价格比较或商品级接入。商品 API 没有配置不会阻断本地对话、需求版本管理和搜索链接生成。

## 七个平台入口

| 来源 | 地区标识 | 商品 API 状态 | 当前站外能力 | 尚未验证 |
|---|---|---|---|---|
| 淘宝 | `CN` | `not_configured`，没有调用 | `https://s.taobao.com/search?q=` | 登录后的商品结果、条件过滤、实际 API 权限 |
| 京东 | `CN` | `not_configured`，没有调用 | `https://search.jd.com/Search?keyword=` | 登录后结果与价格、实际 API 权限 |
| 拼多多 | `CN` | `not_configured`，没有调用 | `https://mobile.yangkeduo.com/search_result.html?search_key=` | 商品结果、App/登录差异、实际 API 权限 |
| Amazon US | `US` | `not_configured`，没有调用 | `https://www.amazon.com/s?k=` | 当前浏览器搜索结果、地区/配送限制、真实商品数据 |
| eBay US | `US` | `not_configured`，没有调用 | `https://www.ebay.com/sch/i.html?_nkw=` | 当前浏览器搜索结果、卖家配送范围、API 生产权限 |
| Walmart US | `US` | `not_configured`，没有调用 | `https://www.walmart.com/search?q=` | 当前浏览器搜索结果、地区/配送限制、商品数据权限 |
| Etsy | `GLOBAL` | `not_configured`，没有调用 | `https://www.etsy.com/search?q=` | 当前浏览器搜索结果、原站地区设置和卖家配送范围 |

所有关键词单独编码；所有来源均没有 `connected_verified` 商品接口状态。本地计划保持 `network_searched:false`、`offers:[]`，附中英文 `sourceCoverageNote`。没有返回商品不表示原平台不存在商品。

`CN`、`US`、`GLOBAL` 表示入口范围，不代表已确认用户所在地、跨境可购或全球配送。切换中英文界面不自动翻译用户原话/搜索词、不改写历史版本、不换汇、不改变预算、不证明配送可行。用户可先检查、精简或编辑关键词，再主动前往原平台；预算关键词不代表平台已执行精确价格筛选。

## 实际核查证据

- 2026-11-04，三个中国平台的独立匿名浏览器核查使用合成“办公椅”：淘宝和拼多多地址返回 200，京东重定向至官方登录页。没有登录、验证码绕过、商品采集或私人数据上传。
- 2026-11-05，四个海外平台使用合成 `desk lamp` 的本机匿名 HTTPS GET：Amazon 503、eBay 403、Walmart 200 但重定向到 `/blocked`、Etsy 403。阻断页不是搜索成功；没有绕过限制或采集商品正文。
- 独立网页研究工具能读取 Etsy 查询页，能找到 eBay 官方查询索引；Amazon 提示 JS/人机验证，Walmart 主页可读而查询不可达。不同工具结果不同，不外推为实际用户浏览器已完成搜索。
- 本轮官方资料、固定模板与完整结果摘要见 [电商替代方案调查](research/COMMERCE-OPTIONS.md)。自动化应用测试应验证 URL 编码、固定域名与实际出站动作；其通过不替代原网站当前可用性。

旧首页/关键词核查和阶段测试原始日志继续保留在私人研发档案，不把后来结果倒写为旧阶段已完成，也不默认公开原始运行日志。

## 账号与后续接入

本轮不创建电商开发账号、不申请商品接口、不读取购物账户、Cookie、AppSecret 或电商密码。AI Key 不提供电商商品数据权限。若未来取得可验证的授权，先审查展示/缓存/再分发范围，再实现独立适配器；不将推广商品池包装成中立全量搜索，佣金不得参与需求符合度排序。

[PRODUCT-SOURCES.md](PRODUCT-SOURCES.md)记录本地搜索计划契约；[调查报告](research/COMMERCE-OPTIONS.md)给出用户提供候选资料、授权商家 feed、独立站合作等后续路线。目前未完成专用商品资料导入或自动跨平台比较功能。

## 分开记录的能力

| 能力 | 当前状态 |
|---|---|
| 固定官方带词 URL 与受控跳转 | 七个平台入口；目标站仍可能因登录、验证、地区或网络限制不可用 |
| 真实商品 API | 七家均未接入 |
| 真实价格/库存抓取、自动跨平台比较 | 未实现 |
| 微信小程序跳转 | 真机/AppID/目标授权尚未验证，当前开发暂停 |
| 生产网络安全与公网多用户 | 未验证；Windows 本地密钥方案不可直接复用公网 |
| 本轮 GitHub 范围 | 用户授权独立公开源码副本；应用AGPL-3.0-only、原创文档CC BY 4.0；不代表公网部署授权 |

依赖安全以[当前安全记录](SECURITY-BLOCKERS.md)为准。旧 55/7 和中间 14 项告警属于历史检查点，不继续误报为当前未修复结果；也不把审计零告警解释为无漏洞或生产安全通过。

## English summary

All seven providers are official keyword-search handoffs only, with product API status `not_configured`, `network_searched:false` and no offers. CN/US/GLOBAL identify entry markets, not verified shipping coverage. Language switching does not translate evidence, change budgets or convert currencies. Overseas anonymous checks encountered access blocks; a correctly generated URL is not proof of live product results. No scraping, affiliate API, automatic comparison or checkout is implemented. This is an authorized public source copy: application code AGPL-3.0-only, original documentation CC BY 4.0. Public service deployment remains outside the validated scope.

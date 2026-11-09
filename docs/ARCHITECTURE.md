# 独立工程架构

apps/client为Taro/React/TypeScript共享客户端，输出H5/weapp；apps/server/src/demand_search为独立Python/FastAPI后端。迁移SQL、依赖、数据库、日志和Git均独立，不依赖相邻NCP环境。

S1包括模型路由/服务、传输、DPAPI、本地安全、历史和SQLite。S2新增AI需求结构、需求路由/服务、不可变版本及独立NCP适配器。模型输出不能自动确认或发布意图。

conversation、message、demand、demand_version分别表示会话、原话、稳定需求和不可变快照。current和confirmed指针分开；内部版本号不等于NCP revision。S3站外搜索计划绑定确定的已确认版本与条目；当前不接商品API，不存商品、价格或自动匹配结果。

解析只取同会话最新原文、分别标注的当前未确认草稿和确认结构，以及有限近期用户消息；外呼不持写锁，返回后重新检查版本/消息状态。确认、撤回、包保存与请求完成标记原子提交。幂等摘要和租约支持恢复，不承诺外部付费exactly-once。

004迁移保留S1历史与凭据，增加需求、版本、请求及协议字节。迁移在BEGIN IMMEDIATE内检查版本；真实库仅在受控实例切换时迁移，开发测试使用独立test-目录。

vendor/ncp只导入按哈希核验的必要Schema、许可、来源及选定语料，不复制运行实现或Git历史。运行时读取应用内固定资产，不访问相邻协议目录。ncp_adapter独立实现Draft2020-12验证及格式断言，拒绝远程Schema解析。

只支持private本地publish/update/withdraw的结构、局部语义、owner、连续revision及撤回终态。确认版本才生成包，保存确切UTF-8字节，不在重复导出时刷新ID或时间。应用来源字段是明示的应用约定，不宣称NCP标准语义。公开名NCP与wire ODIP/0.1.3-exp.1分开，无网络收发或跨实现认证。

本地静态H5同源调用API，开发页不处理真实Key。Key使用当前用户DPAPI；历史和版本仍为SQLite明文。runtime/.local禁止Git；原始报告留本地，精简快照只提供脱敏验证摘要。

原始S0架构决策留本地；当前结构以本页及[验证记录](VALIDATION.md)为准。hosted、多用户和跨端身份未实现，Windows本地方案不能直接部署公网。

S2.1将同一demand扩展为一份多项需求清单，items存于新版本JSON；不回写旧版，不新增数据库迁移。助手式说明从持久化草稿版本及其source_message_id恢复，不由客户端伪造assistant消息。未确认草稿和已确认结构在模型上下文中分开标注。站外search-plan严格绑定已确认版本和项目，不执行外部检索；官方HTTPS关键词入口固定域名、路径与参数白名单，用户查看具体关键词后决定打开或复制；平台是否执行预算过滤、要求登录或实际展示商品另属外部行为。

## 当前客户端与公开边界

一份清单最多30项（含removed），条目ID跨版本稳定，整单预算与单价/单项合计预算分别保存。连续理解默认关闭，在应用界面明确批准会话、模型配置、上下文及费用后才自动解析；授权保存在本页内存，切换或刷新后重新启用。AI生成草稿，整单确认由用户另行完成。助手说明从已保存版本恢复，不额外伪造消息或付费调用。

AppTextarea在H5使用固定高度原生textarea，避免已定位的Taro重挂载高度计算问题；微信仍使用平台textarea，没有修改第三方依赖文件。微信构建只产生受限页面：真实Key和后端连接关闭，平台随机ID、导航、导出、登录与剪贴板须按端验证。Edge手机视口不能证明Safari或微信真机运行。

product_sources/product_routes只生成external_search_plan，network_searched:false、offers:[]。原文、证据片段、Key及其他会话不作为外链参数；不抓取结果、不自动比较商品、不下单。NCP清单字段是应用约定，仍使用ODIP/0.1.3-exp.1与旧包精确字节，不扩大协议兼容声明。

SQLite和DPAPI本地模式不直接开放公网。hosted身份、用户隔离、HTTPS、托管密钥与跨端绑定尚未实现。依赖状态见[安全记录](SECURITY-BLOCKERS.md)。当前为用户授权的公开源码副本，应用AGPL-3.0-only、原创文档CC BY 4.0；本轮结果见[验证记录](VALIDATION.md)。

# NCP S2 本地适配边界与来源

适配基线核验：2026-11-04；说明更新：2026-11-09。已完成选择范围内的Schema、局部语义和本地生命周期验证；没有NCP节点传输、完整上游符合性或跨实现证明，不继承上游测试成绩。

## 固定来源与最小导入

公开项目：[NeedConcord Protocol](https://github.com/David7583/needconcord-protocol)，实验版本0.1.3-exp.1，wire精确保持 `ODIP/0.1.3-exp.1`。S0核验过的公开main为88def78378c9c95f80976f3c11a261019236486d，发布提交为6975ed989d49365453514d7eeb0833feb3138cfb，源码包SHA-256为91a81ee7f278a4346d5e9c4eab42b1109d59997c06f1b3f00f6de8d550278587。这些是固定来源记录，不冒充本次重新查询GitHub当前HEAD。

本次从只读本地研发提交cff62700a63a9ae599d73fdd7ed5245a921326cc导入；导入前验证其工作树干净。21个原文件包括自包含packet Schema、15个合成向量、Apache/CC许可文本、NOTICE、许可范围和来源记录。全部保持原字节；不复制上游实现、.git、.venv、原始ZIP、baseline或内部审计。运行时不读取相邻协议工程。

- 原S0审查记录留在本地研发档案，不进入精简私有快照；实际导入状态以下列导入锁为准。
- [S2导入锁](../config/ncp-import-lock.json)：逐文件路径、固定来源、SHA-256及未修改标记。
- [导入资产说明](../vendor/ncp/README.md)：许可与选择范围。
- [固定规范](https://github.com/David7583/needconcord-protocol/blob/88def78378c9c95f80976f3c11a261019236486d/SPEC-zh-CN.md)：本实现依据第3、15节；未改规范字段。

Schema/机器可读向量按上游有权许可范围适用Apache-2.0；原创说明适用CC BY 4.0，保留第三方与AI辅助来源边界。本应用自身许可证仍须单独决定。

## 支持的应用表示

| 动作 | 本地NCP表示 | 约束 |
|---|---|---|
| 首次确认需求 | intent.publish | 独立intent_id，revision隐含1；原文与确认内容保留 |
| 后续确认修订 | intent.update | 同intent_id，NCP revision严格连续，完整新intent |
| 撤回需求 | intent.withdraw | owner一致，终态；不是删除历史或取消订单 |
| 未确认草稿 | 不生成上述消息 | 不把模型推断当用户已确认 |
| 模拟商家能力 | capability.advertise | 仅合成市场、本地校验，不是第三方能力认证 |
| 模拟候选提案 | proposal.submit | 关联选定已确认intent及模拟商家；不构成真实报价 |
| 结果、回执、commerce | 未实现 | 不输出送达、成交或第三方接入证明 |

应用内部版本序号与NCP revision不同：草稿可以保留多个版本，但只有实际确认并记录的NCP发布/修订消耗NCP修订序号。所有表示固定 `sharing_scope=private`、`allow_aggregate_analytics=false`；无对外发送按钮或隐式网络请求。受控本地导出不改变共享许可，文件由用户自行妥善保管，不应自动传给其他节点。

## 字段与来源映射

原文逐字符保留，模型摘要不能替代。desired_outcome、readiness及明确选择的alternatives_acceptable映射核心字段。替代方案仍为null时拒绝映射，不能静默填false后声称整体已确认。

预算仅在confirmed=true且source不是unknown时映射核心budget_ceiling；未确认预算只保留为带来源的应用注解。没有预算时省略，不能补零。预算是上限，不是价格目标。

required、preferred、unknown、澄清问题、每条来源/证据/确认标志和预算注解保存在：
`constraints.specifications.demand_search_app_v1`，
其format为 `demand-search-app.intent-facts/1`。这是应用自定义约定，**不是NCP标准化的硬约束或来源语义**；第三方可以保留但不能假定理解。interpretation_notes明确该边界。确认整个快照不把仍标为model_inferred/unknown的条目或外部事实改成“已核实”。

会话ID、需求ID、版本ID和消息UUID独立。时间为有效UTC、大写T/Z、最多6位小数；无偏移/闰秒/非法日期。准备采购、点击跳转或确认需求不产生交易或付款承诺。

## 校验API与状态

应用自己的 [ncp_adapter.py](../apps/server/src/demand_search/ncp_adapter.py) 不导入参考库。

- map_intent(original_text, content, user_confirmed=...)：只映射明确确认版本。
- build_packet(...)：生成并验证三种本地消息之一。
- validate_schema(packet)：固定Draft2020-12，启用UUID/日期断言；所有引用离线。
- validate_packet(packet, previous=None)：单包结构、target关联及本地隐私约束。previous=[]表示空历史，完整前序列表则检查状态。
- validate_sequence(packets)：最多1000个本地历史包，核验owner、连续修订、撤回终态和消息ID无重复；不会修改传入数据。
- serialize_packet/parse_packet：稳定UTF-8表示及严格JSON解析。服务应持久化并导出原字节，不为重试刷新UUID、时间或重新序列化。

同一导出历史重复消息ID返回应用错误NCP_MESSAGE_ID_REUSED。它不是协议网络重复回执，也不宣称完成T-02原始请求体幂等接收。网络收发层不存在，因此没有认证、outbox、receipt或对端状态承诺。

本地表示限64KiB和32层；拒绝NaN/Infinity、重复键、BOM、无效UTF-8和孤立surrogate。引用限制是本地安全配置，不改变协议核心Schema。未知非关键extensions作为不透明数据保留，不执行或访问其中URL；commerce语义未支持，明确拒绝该可选能力。Schema SHA-256在运行时核验，远程ref禁止解析。

## 实际验证与复现

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_ncp_adapter.py --junitxml=.local/logs/s2-ncp-tests.xml
```

原S2适配检查记录为52/52通过，其中15个上游选择向量只验证Schema层，其余为应用合成映射、状态、隐私、预算与JSON检查。这是历史检查点，不代表本轮新运行；本轮实际快照成绩见[验证记录](VALIDATION.md)，原始日志留本地。

private-network-intent原用例的网络语义期望为PRIVACY_DENIED。本次只把它用于“Schema有效且可以本地私人保存”，没有把原网络拒绝期望改成网络接受或声称通过网络测试。完整上游manifest及未执行案例未被复制成残缺套件。

| 验证层 | 本应用状态 |
|---|---|
| 已通过Schema验证 | 选择的15个向量及自产正反映射；固定当前wire |
| 本地语义/状态 | 三类private intent的字段关联、owner、修订、终态及表示往返已通过独立测试 |
| 已通过本地独立进程验证 | S1应用HTTP/存储有自身证据；**NCP节点传输尚未验证** |
| 已通过真实网络安全验证 | 尚未验证 |
| 已通过跨实现互操作验证 | 尚未验证 |
| 尚未验证 | 其余核心消息、可选商业/履约语义、对外授权、全套符合性、NCP网络传输及跨语言/跨组织互操作 |

协议缺陷单独向上游提出，不由应用静默修正Schema。依赖修复与风险见[安全状态](SECURITY-BLOCKERS.md)。本地NCP测试不替代供应链或生产安全验证；当前公开副本已获授权，应用代码AGPL-3.0-only、原创文档CC BY 4.0；NCP原许可不变。

## S2.1 多商品应用约定

多商品仍映射为一个清单 intent，不改变 ODIP/0.1.3-exp.1、上游 Schema 或包大小限制。非空清单追加到 constraints.specifications.demand_search_app_v1.shopping_list，结构为 {format: "demand-search-app.shopping-list/1", budget_scope: "whole_list", items: [...]}。items 使用应用内稳定 UUID，保留数量、来源、确认标记、单项预算及 active/removed 状态。此处不是 NCP 核心标准化的多商品语义，未理解该应用约定的实现仍须自行判断支持范围；不声称自动跨实现商品匹配。

顶层核心 budget_ceiling 仅表示已确认的整份清单总预算，单项预算不冒充总预算；各项预算与口径只进入应用注解。原文、未知项和逐项来源保留。旧版无清单时不添加 shopping_list 字段；已持久化的历史 packet_bytes 完全不重建。超64 KiB确认失败并回滚，没有截断、拆包、自动放宽限制或对外传输。

## 独立模拟市场（2026-11-09）

新增市场模块只复用固定 Schema 验证器，不扩大原 intent 生命周期校验器的三类消息白名单，也不修改上游协议文件。500 家商家分别生成能力声明；按已确认需求查询时，候选生成关联同一 intent_id 的模拟提案。协议必填字段和该角色适用信息有实际数据，不为“填写全部协议”伪造需求、成交、付款、履约或回执。

商家目录是可复现的合成输入；其本地持久化不包含用户需求原话或查询历史。提案查询读取所选需求版本，不覆盖已确认内容。用户若把候选反馈到对话，仍需按既有交互确认修订。

此扩展证明特定结构可以被当前应用生成、查询和关联，**不能证明500家真实商家接入、500个独立节点、协议全套符合性或跨实现互操作**。市场匹配是应用逻辑，类别、规格、评分依据等应用字段不因放进NCP表示就自动成为协议标准。商业扩展、生产网络认证与真实履约仍未实现。复现与覆盖见[模拟市场说明](SIMULATED-MARKET.md)和[验证记录](VALIDATION.md)。

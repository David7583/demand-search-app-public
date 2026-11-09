# 模拟市场 / Simulated market

本机、单用户、完全合成的可复用市场。所有商家、商品、服务、价格、地区、参数与交期都是测试场景数据，不对应真实商家、资质、库存或报价。当前不收发真实商家的协议消息，不调用电商API、模型、支付或第三方网站。

## 使用

1. 启动应用，在顶部导航打开 **模拟市场 / Simulated market**。无需配置模型即可浏览；若首次打开模型向导，先点击“返回主界面”。按关键词或分类搜索，使用上一页/下一页翻页。
2. 点击 **商家详情与 NCP** 查看该商家资料、三项供应内容及 capability.advertise JSON。
3. 在现有对话中形成清单，检查并明确确认需求版本。在 **方案工作区** 的 **查询模拟市场** 区域点击 **查找模拟候选**。
4. 系统逐项显示最多三条候选，展示关键词依据、模拟预算状态及未核实条件。表单若有未保存编辑，查询仍使用标注的已保存版本。
5. 查看 proposal.submit JSON；选择 **带回对话讨论** 只准备带版本引用的待发送意见，不自动发送、调用AI、确认方案或采购。
6. 中英文切换只改变界面与预设目录文案，不翻译或改写真实需求。官方电商搜索入口仍是独立功能，没有用模拟结果冒充真实平台结果。

检索使用确定性的中英文关键词/别名，不会根据任意描述自动生成虚构候选。没命中表示当前模拟目录没有识别到关键词，不代表真实市场没有供应。硬约束未验证，不显示假精确的符合百分比；排序不使用佣金。

## 在AI对话中了解市场

可询问“已有多少商家和商品？”、“有哪些品类？”或“其中有AI硬件、大型设备和软件服务吗？”。普通需求理解与连续流式对话共用模型调用入口，会附带从本地市场数据库读取的概况：商家总数、供应项总数、领域总数及每类的中英名称和数量。不会把1500条完整商品或真实会话一起额外塞进此概况。

**1500是商品/服务供应记录数，包含不同商家的变体；50是领域数。** 不把1500说成1500种独立品类。概况只供AI解释市场范围，不是用户确认事实、真实报价或某次检索结果。具体候选仍需使用模拟市场查询。

未初始化、损坏或不可读时，概况明确不可用、数量未知；模型不得把它说成0家或继续编造统计。首次安装可先打开模拟市场建立独立库。使用已有模型配置和外部处理授权，不为更新概况额外调用模型。

English: Both normal parsing and streamed conversation receive a read-only summary of the actual local market: merchant and offering totals, category totals and bilingual category counts. Offerings include services and merchant variants; they are not distinct product categories. An unavailable database yields unknown counts rather than invented or zero totals. The summary is application context, not user-confirmed requirements or evidence that products were searched.

## 数据与复用

- **50 个领域 × 每领域 10 家 = 500 家商家；每家 3 项 = 1500 项供应内容**。覆盖日常消费、家居与建设、出行、文化、健康辅助、AI设备、计算机与软件、专业服务、农业和大型工业设备。
- 目录定义与确定性生成器在 [market_catalog.py](../apps/server/src/demand_search/market_catalog.py)，中文、英文、规格、价格、交期与业务类型随类别和样本变化。名称均明确虚构，不冒用真实组织。
- 独立数据库：项目下 `runtime/simulated-market.sqlite3`；原会话库仍是 `runtime/demand-search.sqlite3`。日常运行库不提交Git；另外提供[专门生成的脱敏模拟快照](../data/simulated-market/README.md)，可在另一台电脑使用或由目录源码重建。
- 第一次查询自动建库。以后核验种子版本、内容摘要及SQLite完整性后复用，重启不重建或清空。
- 市场库只存目录和元数据，不存用户原话、需求版本、查询或模型Key。匹配对主会话库只读；结果反馈按现有会话机制由用户决定是否保存。
- 遇到种子版本或内容失配返回 `SIMULATED_MARKET_INTEGRITY`，不会静默覆盖。遗留初始化锁文件返回 `SIMULATED_MARKET_BUSY`；先确认没有初始化进程并保留数据，再处理。
- 若以后修改目录，应更新种子版本并规划迁移；当前不是商家后台或任意数据库编辑器。

手动初始化或核验：

~~~powershell
./.venv/Scripts/python.exe scripts/init_simulated_market.py
~~~

重复执行是幂等核验。脚本的 `--rebuild` 是明确替换市场库的维护操作；仅在决定放弃现有市场快照并已备份后使用，不用于日常启动，不重建会话库。不要在服务同时处理请求时重建。

## GitHub 数据库快照

按用户明确授权，额外提交 `data/simulated-market/market.synthetic.sqlite3`。该文件在全新隔离目录从固定种子生成，仅包含商家目录与市场元数据；没有从日常数据库复制或抽取。这里的脱敏方式是全合成数据隔离，不是用真实商家/用户数据做简单改名。

快照与日常 `runtime` 分离；Git仅对这个确切文件开放例外，其他SQLite、会话库、配置、Key、日志和备份继续排除。上传前核验库中只存在预期的两张表，并核对完整数据与生成器一致。文件摘要和复用步骤见[快照说明](../data/simulated-market/README.md)。

## NCP 表示边界

wire保持 `ODIP/0.1.3-exp.1`，上游Schema字节不变。角色适用的能力声明与候选提案经固定Schema校验，并明确标记 `data_origin=synthetic`、`local_only=true`、私人范围和种子版本。报价是基础单位模拟价格，不把数量或整单预算隐藏合并进单价。

每家能力声明关联自己的供应项；查询所选已确认版本对应的真实本地intent记录后，提案关联其intent_id、版本和清单项。未经确认、其它会话的版本及撤回需求被拒绝。提案的场景时间不早于关联需求，标记为模拟时间，不声称真实报价或接收事件。

完整角色信息不意味着伪造所有消息类型。本功能没有虚构订单、支付、履约、outcome.report或receipt.ack。500家样本都由同一应用生成，不是500个独立实现或节点。Schema验证不等于跨实现互操作、全套NCP符合性或生产网络安全。

预算只在单项预算已确认、币种一致、单位及预算口径明确时比较；合计口径还需要数量。不换汇、不分摊整单预算，不把未知预算记为零；运费、税费、配送与真实供应能力始终未核实。

## 必要验证入口

本轮只运行下面的专项流程，不为此重复原340项后端及整套浏览器检查：

~~~powershell
./.venv/Scripts/python.exe -m pytest tests/test_simulated_market.py
npm.cmd --prefix apps/client run typecheck
npm.cmd --prefix apps/client run lint
$env:DSA_CLIENT_BUILD='staging'
npm.cmd --prefix apps/client run build:h5
Push-Location apps/client
npx.cmd playwright test --config playwright.market.config.ts
Pop-Location
Remove-Item Env:DSA_CLIENT_BUILD
~~~

专项浏览器只使用合成服务与独立18006端口，不使用日常8000会话或真实Key。实际结果记录在[验证说明](VALIDATION.md)；本机原始日志位于 `.local/logs/simulated-market`，不进入私有仓库。

## English

This is a separate, reusable local SQLite catalog of **500 fictional merchants across 50 categories and 1,500 synthetic offerings**. Open **Simulated market** in the top navigation to browse without an AI key. Merchant details expose NCP capability JSON. Select a confirmed requirement version in **Solution Workspace** to obtain up to three candidates per item, with keyword evidence, budget status, unresolved conditions and NCP proposal JSON.

All data is synthetic. Matching is deterministic keyword/alias matching, not live product retrieval or proof that requirements are satisfied. Proposals are linked to the selected confirmed intent. Returning a candidate to chat prepares unsent feedback and never confirms, purchases or calls AI automatically.

The market database is separate from the conversation database. It contains no user queries, conversations or credentials and survives restarts. Version/hash checks reject unexpected changes without resetting data. The repository contains the reproducible catalog, initializer and a separately generated sanitized synthetic database snapshot. Daily-use runtime databases remain excluded. Run the initializer above to create or verify the store. Explicit rebuild replaces only the market snapshot and requires a deliberate backup decision.

The wire identifier and pinned NCP assets remain unchanged. Capability/proposal schema validation and local application links do not establish independent merchant adoption, network interoperability, transaction completion or production security. This public copy licenses application code under AGPL-3.0-only and original documentation/catalog data under CC BY 4.0; upstream NCP licenses retain their original scope.

# 来源、修改与版权边界

**简体中文** | [English](PROVENANCE.en.md)

本记录适用于 **NeedConcord Protocol 0.1.3-exp.1** 公开源码，其 wire 标识为 `ODIP/0.1.3-exp.1`。项目由 **David7583** 发起并主导设计，作为初始维护者；研究、编写和验证过程中使用了 AI 辅助。公开展示名不对应未经确认的真实姓名或机构。

发起者授权仅覆盖其原创或依法有权授权的内容。AI 辅助不自动证明素材可受版权保护、全部原创、绝无第三方相似表达或完全排他的权属；没有对这些事项作无条件保证。其他作者、库作者和许可文本权利人保留各自权利。

## 公开材料来源

| 材料 | 可观察来源与修订 | 权利边界 |
|---|---|---|
| `SPEC-zh-CN.md`、`BUSINESS-BOUNDARY.md`、版本/迁移说明 | 基于发起者提供的 v0.1.2 草案继续修订，保留目标；新规则与差异见 PROTOCOL-DELTA | 有权许可的规范文字按 CC BY 4.0；历史创作链没有完整独立证据，不声称全部原创已证实 |
| `schemas/` 与原有七份 `examples/` 的派生内容 | 从同一草案的 Schema 与模拟示例修订；Schema 含修改通知 | 在可授权范围内 Apache-2.0；示例不是实际用户、商品、合同或第三方接入数据 |
| `tests/fixtures/v0.1.2/` | 为迁移与兼容性保留的最小旧版 Schema 和模拟输入，逐项来源随夹具提供 | 不扩张至未经授权的历史/第三方权利；不包含完整研发档案 |
| `odip/`、`reference/`、`scripts/`、新增 `tests/`、公开向量 | 按规范编写的 AI 辅助参考代码、自动化与测试资产；不把两个同库进程算独立实现 | 有权许可的代码、测试和机器可读素材按 Apache-2.0 |
| README、贡献/治理/安全文档、教程、社区模板与讨论草稿 | 按本项目需要撰写，未复制第三方社区准则模板全文；公开事实与操作说明在相关段落注明来源 | 原创说明按 CC BY 4.0；代码/配置部分按 Apache-2.0；第三方引用仍属原来源 |
| `LICENSE`、`LICENSES/CC-BY-4.0.txt` | 官方 Apache-2.0 与 CC BY 4.0 完整许可文本 | 保留原文本，不冒充本项目作品，不暗示 Apache 或 Creative Commons 认可本项目 |
| `LICENSES/dependencies/` | 从锁定依赖分发物中提取的上游许可/版权告知 | 依各上游许可；项目许可不覆盖这些库代码 |
| `evidence/` | 对公开源码快照实际运行后生成的脱敏测试输出、计数和摘要 | 执行事实；不是身份、来源、交易真实性或第三方认证证明 |

依赖版本、SHA-256、上游许可字段与文件名见 [LICENSES/dependency-licenses.json](../LICENSES/dependency-licenses.json)。源码包不携带解释器、虚拟环境、下载 wheel 或真实业务数据。未来若分发二进制/容器/vendored 库，必须重新审查实际嵌入组件及其完整告知，当前包级审查不能代替该工作。

## 历史资料与不确定性

v0.1.2 完整草案、原始压缩包、内部环境信息与历史测试/审计记录由维护者离线保留，未默认包含在公开仓库。公开修订记录与最小迁移夹具保留必要的可追溯性；运行公开符合性测试无需访问维护者的内部资料。

原草案没有完整逐段创作记录和第三方来源清单。已读取材料中，除标准许可证文本与引用的公开事实外，未识别到有明确第三方版权头的代码片段；**未发现不等于证明不存在**。原草案中的平台名称只是示例，不表示其接入、合作或授权。历史示例的用户确认/交易声明均按模拟数据处理。

若后续确认某段内容来自第三方，应保留其作者、原许可、来源与修改说明；不能仅因 AI 参与而删掉来源。无法取得必要许可的材料须停止分发该部分，选择替换、删除或另获授权，再重跑受影响测试。未核实来源不能直接标为 David7583 的原创。

公开名称 NeedConcord Protocol 与历史工作名 ODIP 指同一项目，改名不改变许可证或技术兼容性；版权许可不授予商标排他权。规范变更记录不等于证明与旧版或其他组织自动兼容。适用范围见 [LICENSE-DOCS.md](../LICENSE-DOCS.md) 与 [NOTICE.md](../NOTICE.md)。

## English

David7583 initiated and leads the design of this project and is the initial maintainer. AI assisted research, drafting and validation. Copyright notices and licenses apply only to original or lawfully licensable material in which the holder has rights. Historical provenance is not fully independently established. Third-party notices remain in force; uncertain material is not represented as the initiator's exclusive work. Full private development archives are excluded; the public package includes the specification, implementation, public tests and minimum documented compatibility fixtures needed for independent use.

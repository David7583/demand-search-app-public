# S1 历史会话与接续

历史功能不依赖 AI Key 或模型可用性。本地用户原文先写入本工程 SQLite 后才返回成功；配置失败、切换模型不会清空会话。

## 数据与运行边界

- 只使用本项目 runtime 数据库，通过003迁移新增 conversations / conversation_messages；不使用NCP数据库或协议消息作为内部唯一存储。
- local-dev身份由服务端固定为local，不从请求接受owner_id；其他owner记录不可通过这些接口读取、修改或删除。hosted模式仍禁止启动，这不是已完成公网多用户认证的声明。
- 每次写操作用BEGIN IMMEDIATE完成归属检查、幂等判断、序列分配和保存；失败回滚。同一client_message_id重投同会话同原文返回duplicate，异文或跨会话重用返回MESSAGE_ID_CONFLICT。
- 新会话不复制旧会话消息或条件；原文空白/换行保留，已存消息不被模型摘要覆盖。标题可单独修改。
- SQLite secure_delete开启；这不能保证操作系统缓存、磁盘快照或用户备份被物理擦除。文件ACL、全盘加密和备份治理另行评估。

## API与上限

所有路径以/api/v1开头，集成后的主应用负责本地session与CSRF保护。

| 路径 | 合同 |
|---|---|
| GET /conversations?query=&limit=50&offset=0 | 返回conversations和total；按更新时间倒序；标题/原文做字面匹配搜索，不把%和_当通配符 |
| POST /conversations | 可选title，返回空会话detail |
| GET /conversations/{id} | 返回完整消息，按sequence排序 |
| PATCH /conversations/{id} | 仅改title |
| POST /conversations/{id}/messages | content及UUID client_message_id；返回message和duplicate |
| DELETE /conversations/{id} | 删除该会话及关联消息 |
| GET /conversations/{id}/export | 导出单会话的机器可读JSON |
| GET /me/export | 导出所有本地会话；不导出模型配置或密钥 |
| DELETE /me/data | 只删除本地会话/消息；明确保留AI配置，删除配置使用独立配置接口 |

S1本地上限：200个会话，每会话500条消息，每条8000个Unicode字符；标题120字符，搜索文本200字符，列表每页最多100项。超限明确返回错误，不静默截断保存原文。此限制不是压力测试结论。导出包含私人会话内容，保存与分享由用户自行决定；接口不读取模型秘密表。

## 模型上下文与归属

内部get_context只读取指定会话，默认最近6条、总内容6000字符；限制可下调，最高20条/12000字符。若截断单条上下文，会标truncated=true；数据库原文不变。不同会话不共享上下文，也不会把整库历史传给AI。

内部record_assistant可追加回复，仅允许model、configuration_id、source归属元数据；source为ai或local-status。parent_message_id若提供必须指向同会话user消息。该方法没有公开写入路由，客户端不能伪造assistant角色。外部AI发送仍需用户同意；历史保存与模型调用是两项独立操作，模型失败不能撤销已保存原文。

## 独立测试

使用项目.venv运行：

```powershell
./.venv/Scripts/python.exe -m pytest tests/test_history.py --junitxml=.local/logs/s1-history-tests.xml
```

全部测试使用runtime/test-history-*的合成记录，结束后只清理确认在本项目runtime内的专用测试目录；不读取用户已有runtime数据。覆盖A/B隔离、重启与子进程恢复、并发序列与幂等、跨会话冲突、归属拒绝、字面搜索/分页、上下文边界、删除/导出和配置保留。路由单测独立挂载；主应用cookie/CSRF/HTTP/浏览器验证由集成测试另行执行。

本模块没有宣称完成需求不可变版本、NCP映射、商品检索、模型真实连通或跨端账号绑定；这些按各自阶段与证据验收。

## 已验证的安全边界

本机 HTTP 层已通过合成请求检查：非回环客户端、跨源请求、缺失或错误的会话/CSRF 校验及超过限制的 JSON 请求会被拒绝；迁移的版本检查与执行现已处于同一个 SQLite 写事务，确定性并发回归确认两个并发初始化调用不会重复执行同一迁移。此结果是本地实现验证，不代表生产渗透测试或多用户认证验收。

Windows DPAPI 仅用于保护 AI API Key，使用当前 Windows 用户范围，并已用合成凭据验证解密、篡改拒绝和上下文绑定。**历史会话正文与标题当前存放在未加密的本地 SQLite 中**，不属于 DPAPI 保护范围。`owner_id=local` 是应用内部归属约束，不是操作系统用户之间的访问隔离；能够直接读取数据文件的进程仍可能读取会话。不要把文件归属检查、CSRF 或密钥加密表述为历史数据库已完成静态加密。

当前仅支持本机使用；没有证明公网安全、跨设备身份隔离、备份彻底删除或对本机恶意程序的防护。原S0告警和后续修复分别记录，见[安全状态](SECURITY-BLOCKERS.md)及[验证记录](VALIDATION.md)。自动化历史测试使用合成数据；真实AI连通通过应用界面由用户验证。

# AI 初始化与模型配置（S1，本地 Windows）

当前实现是单用户本机开发适配。首次打开应用后，在“AI 配置”页选择服务商、确认 API 地址、输入 Key、读取模型目录或填写模型 ID，再运行需求解析测试。只有解析成功后点击“保存并设为默认”才会切换配置。无需、也不应把真实 Key 发送给 Codex。

本阶段没有预设“肯定可用”的模型列表。目录来自实时服务商接口；目录中存在一个 ID 不代表当前 Key 有调用权限，也不代表模型支持文本生成或本次结构化输出。目录不可用时可手动填写 ID，然后通过真实测试验证。

## 已实现的服务商适配

| 服务商 | 默认 Base URL | 生成接口 | 模型目录 |
| --- | --- | --- | --- |
| OpenAI | https://api.openai.com/v1 | Responses 默认；也可选择 Chat Completions | GET /v1/models |
| DeepSeek | https://api.deepseek.com | Chat Completions | GET /models |
| Kimi / Moonshot | https://api.moonshot.cn/v1 | Chat Completions | GET /v1/models |
| 通义千问 / 百炼 | https://dashscope.aliyuncs.com/compatible-mode/v1 | Chat Completions 兼容模式 | 原生 GET /api/v1/models |
| 自定义兼容接口 | 用户填写 | Chat Completions 或 Responses | Base URL + /models，缺失时手填 |

百炼官方目前推荐按业务空间及地域使用控制台提供的 API 地址，旧版 DashScope 地址仍受支持。可修改默认值；Key 必须与地域匹配。目录读取仅返回接口当前首批结果，不遍历目录的分页；用户可填写目录之外的模型 ID。Kimi 可选择官方中国或国际站 API 地址，Key 与站点须匹配。

内置服务商限制为已知官方域名；第三方中转服务应明确选为“自定义”。自定义地址只允许公开 DNS 域名的 HTTPS 443 接口，不支持本地 Ollama、内网地址或 HTTP。使用自定义接口时，Key 和需求正文将发送至该域名，用户须自行确认服务商可信。

## 测试与保存行为

1. 获取模型目录会发送 Key；不会发送需求正文。
2. “测试连接”会发起一次真实模型生成请求，可能产生服务商费用。它同时验证鉴权、模型响应和需求结构，返回请求模型、实际响应模型、状态和解析结果。没有只凭 HTTP 200 即判成功的路径。
3. 保存前先确认系统密钥保护可用，再请求模型。解析成功后生成有效期十分钟、只能使用一次的验证票据。票据内 Key 已加密，未激活为配置。
4. “保存”显式消费票据并写入配置。失败、票据过期或并发编辑不覆盖之前的配置。并发消费同一票据最多成功一次。
5. 修改配置时允许不再输入 Key，但仅在服务商和规范化 Base URL 完全相同时复用；更换地址必须重新输入，避免把原 Key 静默发往其他服务。
6. 可切换默认配置、删除配置。删除正在使用的配置后，默认配置为空，应用不会自行选择另一个服务商。
7. 验证时间表示曾成功完成该次调用；之后额度、模型授权或 Key 状态可能变化。普通需求解析仍会进行真实调用并返回诊断。

应用把用户原话绑定为 `original_text`，不允许模型改写原文。模型声明的显式来源必须有原文逐字证据，而且字段文字必须出现在证据中；否则降级为推断。结果始终 `user_confirmed:false`，不是购买承诺、用户授权确认或经验证的外部事实。本预览结构是应用内部结构，不表示完成了 NCP wire 消息映射或全面兼容认证。

## 密钥与网络边界

- Windows 运行时由当前用户 DPAPI 加密 Key，写入项目自己的本地 SQLite；不回退明文存储。测试替身仅用于合成测试。
- API 不返回 Key 或末尾字符，只返回固定“已安全保存”。Key 不进入前端构建产物、浏览器 localStorage、Git、请求日志或模型提示。
- 解密后的 Key 只用于本次服务端调用；Python 字符串不能保证即时物理内存擦除。当前 Windows 账号被控制、调试器或内存转储不在 DPAPI 的防护能力内。
- 待保存票据十分钟失效；列出配置或再次测试时清除过期票据。删除配置清除相关票据。数据库和备份都应视为敏感文件，禁止公开。
- DNS 返回的全部 IP 都须为公网地址；混合公网/私网也拒绝。连接固定到已经校验的 IP，保留原域名 TLS SNI 和证书校验，防止 DNS 二次解析变更目标。
- 不使用环境代理，不跟随重定向，不关闭 TLS 校验；禁止 URL 凭据、查询参数、片段、IP 字面量及保留网络。已授权域名解析到私网时同样拒绝。
- DNS 等待五秒；HTTP 总期限约四十五秒，单次 socket 等待不超过十五秒；没有自动重试。响应上限 512 KiB，拒绝非 JSON、重复键和非有限数值。不接受压缩响应。
- 固定安全错误码区分鉴权、权限、额度、端点、DNS、TLS、超时和模型结构错误。不上报上游原始错误正文。恶意模型响应中的完整 Key 会被替换为 `[REDACTED]`。
- OpenAI Responses 使用 `store:false` 和严格结构化输出。此参数不能替代服务商的数据政策。其他接口不承诺零保留；需求内容会按用户同意发送给所选服务商。
- 未向模型开放工具，不自动调用购物接口，不自动下单。

H5 与微信小程序共用配置 API 合同；当前本机的 Cookie/CSRF 会话及 Windows DPAPI 不代表小程序公网多用户部署方案。未来公网版本需要用户身份与授权隔离、托管密钥/KMS、TLS、独立滥用与计费控制，不能直接公开当前本地服务。

## API 合同概要

所有路径以 `/api/v1` 开头，并受应用本地会话和 CSRF 保护。

- `GET /config/providers`：服务商能力及默认地址，不含模型库存。
- `GET /config/models`：脱敏配置与默认 ID。
- `POST /config/models/discover`：按草稿凭据读取目录。
- `POST /config/models/test`：一次真实解析；成功返回验证票据及结果。
- `POST /config/models/save`：消费票据后新增或替换配置。
- `POST /config/models/{id}/activate`、`DELETE /config/models/{id}`：切换与删除。
- `POST /config/parse`：使用指定或默认配置解析需求。

请求必须明确 `consent:true` 才能发送数据。草稿字段为 `name,provider,base_url,api_mode,model,api_key,existing_id,consent,test_text`；修改时 `api_key` 可省略。保存字段为 `validation_id,make_active`。不接受未知字段。

## 验证状态与官方依据

独立自动化测试使用明确标注的合成 Key、合成模型和模拟传输，验证配置事务、持久化、幂等票据、隐私边界、结构输出及网络限制。它们不是 OpenAI、DeepSeek、Kimi 或百炼的真实接入成功证明。实际可用模型、地区权限和付费调用仍须用户在应用界面输入 Key 后确认。依赖历史及后续修复状态见[安全阻断项](SECURITY-BLOCKERS.md)；本文件不宣称已具备公开部署条件。

实现依据在 S1 开发时查阅的官方页面；服务商 API 后续可能变化：

- [OpenAI 模型目录](https://developers.openai.com/api/reference/cli/resources/models/methods/list)
- [OpenAI Responses 结构化输出](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [DeepSeek 模型目录](https://api-docs.deepseek.com/api/list-models/)
- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)
- [Kimi Chat API](https://platform.kimi.com/docs/api/chat)
- [Kimi 模型目录](https://platform.kimi.com/docs/api/list-models)
- [百炼 OpenAI 兼容接口与地域](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)
- [百炼模型目录](https://help.aliyun.com/zh/model-studio/list-models)


本机可复现命令（必须使用本项目解释器）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_models.py tests/test_provider_transport.py -q
.\.venv\Scripts\python.exe scripts/smoke_models.py
```

第二个命令启动专用测试服务两次，通过真实回环 HTTP 验证配置与重启生命周期，并使用真实 Windows 当前用户 DPAPI。AI 服务商响应仍是明确的合成测试替身，不会访问外部接口。工厂仅接受 `runtime/test-model-http-<UUID>`，没有生产环境“启用模拟模型”的开关；测试数据和日志保存在本项目被忽略的目录中，不读取真实用户数据库。结果写入 `.local/logs/s1-model-http.json`，子进程与控制台日志使用同一前缀。

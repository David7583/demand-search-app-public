# 安全与报告 / Security

Windows本地实验应用，只绑定127.0.0.1，hosted模式拒绝启动。本仓库是公开实验源码，**不代表公开部署或公网多用户处理已经获准或通过验证**。

## 密钥与资料

Key只在本地同源配置页输入，以Windows当前用户DPAPI加密，不进入前端源码、浏览器持久存储、Git或明文日志。运行期间仍存在内存；此方案不能防御已控制本机账户的恶意程序、管理员或调试器。

原话、草稿、确认版本和本地NCP包是SQLite明文，runtime/.local由本机权限保护。真实数据库、Key、日志、备份和私人导出不进入源码仓库。语言偏好不包含Key或会话正文。

AI外部处理须界面明确同意。官方搜索只在用户打开时发送可见关键词，可能包含私人条件，应先检查；不索取电商密码/Cookie，不接商品或联盟API，不绕过目标站点限制。

## 验证范围

已有本地会话/CSRF、同源与Host、HTTPS服务商地址和DNS校验、输入输出上限、限流、错误去敏、数据归属、幂等与秘密扫描。合成模型和本机测试不证明生产安全或多用户隔离。

此前桌面修复记录为完整/生产npm审计均0项；原55项/7 critical和中间14项是本地历史证据。本轮复查结果见[验证记录](docs/VALIDATION.md)。维护包保留原许可、来源及重建材料，仍需跟踪上游公告；0公告不是无漏洞保证。见[安全状态](docs/SECURITY-BLOCKERS.md)。

## 报告方式

维护者：**David7583**。普通问题可提交公开Issue，但不要在Issue/PR中上传Key、私人会话、数据库、完整日志或漏洞利用细节。

敏感安全漏洞请使用本仓库的 [私密漏洞报告入口](https://github.com/David7583/demand-search-app-public/security/advisories/new)。该入口与公开Issue分开。若入口不可用，可先提交不含漏洞细节的协调请求，待维护者安排私密渠道；不使用虚构邮箱。

## English summary

Loopback-only, single-user Windows application. Keys use current-user DPAPI; conversations remain plaintext in protected local SQLite. Public source does not make this a secure hosted or multi-user service.

Use public Issues only for non-sensitive problems. Report sensitive vulnerabilities through [Private Vulnerability Reporting](https://github.com/David7583/demand-search-app-public/security/advisories/new). Do not post credentials, private conversations or exploit details publicly. If that entry is unavailable, request confidential coordination without revealing details. No dedicated email address is invented.

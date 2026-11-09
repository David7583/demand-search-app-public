# Demand Search App 客户端

[中文项目说明](../../README.md) | [English overview](../../README.en.md)

Taro/React/TypeScript客户端，以Windows本地桌面浏览器为当前目标。微信共享代码保留，移动端和真机工作暂停。

从项目根运行：

```powershell
npm.cmd --prefix apps/client run build:h5
./scripts/start-local.ps1
```

访问http://127.0.0.1:8000，首次按向导配置模型，之后从设置修改。Key只在同源本地页输入，后端DPAPI保护；不进入浏览器持久存储、前端源码或日志。10086开发页和微信开发产物不接受真实Key。

桌面提供AI对话、方案工作区、并排视图和折叠侧栏。连续AI需当前会话明确授权；草稿与确认版分离，历史引用随消息保存。中文/English只切换界面，不翻译原话、历史、关键词或协议数据。

官方搜索支持中国（淘宝、京东、拼多多）、美国（Amazon、eBay、Walmart）、国际（Etsy）。市场与界面语言独立；无商品API、抓取、真实价格/库存或自动比价，不自动换汇或确认配送。

```powershell
npm.cmd --prefix apps/client run lint
npm.cmd --prefix apps/client run typecheck
npm.cmd --prefix apps/client test
$env:DSA_CLIENT_BUILD='staging'
npm.cmd --prefix apps/client run build:h5
npm.cmd --prefix apps/client run test:browser -- --project=desktop-edge
Remove-Item Env:DSA_CLIENT_BUILD
```

staging输出.local/s2-client，浏览器使用专用回环端口、隔离test-数据和合成模型，不操作8000上的真实会话/Key。默认构建输出apps/client/dist。

实际结果见[验证记录](../../docs/VALIDATION.md)，依赖历史见[安全状态](../../docs/SECURITY-BLOCKERS.md)。既有0公告不代表本轮重新审计或生产安全。应用许可待定，本轮仅私有源码保存获授权。

# 独立环境和复现

Windows x86_64、CPython **3.12.7**、Node **24.18.0**、npm **11.16.0**。本项目 .venv 独立，include-system-site-packages=false；不修改全局PATH、Conda或NCP环境。用户配置、历史与密钥均在本项目内。

Python锁现在包含29个固定包与wheel SHA-256。S2仅新增独立Schema校验所需jsonschema4.23.0、attrs26.1.0、jsonschema-specifications2025.9.1、referencing0.37.0、rpds-py2026.9.1；从官方PyPI下载、按固定hash验证，再安装到本项目.venv。未共享NCP的site-packages。许可元数据见dependency-licenses-python.json，不代替最终公开许可审查。此前桌面收口检查记录（不代替本轮新核验）：锁清单653项（含其他平台可选包），Windows实际安装573个包，npm审计计574项（含根包），完整与omit=dev均0项公告。原55项/7 critical、14项中间记录保留。三个file:tooling维护包必须和锁一起保留，.npmrc固定install-links与严格peer解析；npm ci使用本项目缓存。不代表生产安全或公开发布批准。

```powershell
./scripts/init.ps1 -Python python
./.venv/Scripts/python.exe scripts/verify.py --stage S5 --target desktop --browser
./.venv/Scripts/python.exe scripts/smoke_launcher.py
# 默认构建部署到本项目本地静态目录：
npm.cmd --prefix apps/client run build:h5
./scripts/start-local.ps1
# http://127.0.0.1:8000
./scripts/stop-local.ps1
```

verify自动使用DSA_CLIENT_BUILD=staging，把H5/weapp编译到.local/s2-client，浏览器使用合成provider测试工厂、随机test-s2-browser-目录及18000端口；不覆盖用户正在使用的静态包。该测试工厂只接受synthetic-s2-only-凭据，禁止8000端口；没有生产mock开关。默认手动build仍输出apps/client/dist。

正式本地升级先验证，再停止自身8000实例，将SQLite备份保存到受保护的.local，部署同版本H5并启动，执行004迁移。不要清空runtime或把S1旧库直接替换成测试库。新会话Cookie会随进程重启失效，刷新可重新建立，已保存Key不需要重输。

启动脚本使用隐藏进程，核对当前项目venv与其解释器子进程、端口及脚本路径；不会停止其他项目进程。runtime/.local ACL仅当前Windows用户与SYSTEM；不修改全局安全设置。DPAPI是当前用户作用域，备份迁机不保证可解密。

runtime为项目SQLite；.local存放本地基线、缓存、备份与原始证据；均被Git排除。DSA_MODE只允许local-dev。测试DSA_DATA_SUBDIR只接受test-目录；不自动加载.env，不存明文Key。10086开发页与微信端不接受真实Key。

S2统一日志位于.local/logs/s2-validation，独立模块与浏览器证据为s2-*。S0/S1阶段报告保留，后续验证不覆盖旧阶段统一日志。重复S2验证会更新同名S2日志，阶段固化时保存摘要和hash。所有自动化均为合成输入，不调用真实付费模型或读取用户会话。

浏览器验证使用Edge桌面/手机视口，不等于手机或微信真机。GitHub Actions定义限定桌面验证，实际执行以[验证记录](VALIDATION.md)为准。Starlette/httpx弃用提醒保留；测试成功不证明生产安全。

## S5 受控前端构建入口

前端不再安装通用Taro CLI，改用固定@tarojs/service 4.3.2和本项目apps/client/scripts/build.mjs。仅支持h5/weapp与可选--watch，禁用全局Taro配置、模板下载和任意CLI命令。npm run build:h5/build:weapp命令保持不变；DSA_CLIENT_BUILD=staging仍输出.local/s2-client，默认输出本项目dist。

采用前先在.local隔离目录做完整安装与双端构建；采用时执行npm ci --ignore-scripts，只使用项目缓存，没有执行依赖生命周期脚本或更改系统Python/Node。复现本轮安装：

```powershell
npm.cmd --prefix apps/client ci --ignore-scripts --cache .local/npm-cache
$env:DSA_CLIENT_BUILD='staging'
npm.cmd --prefix apps/client run build:h5
npm.cmd --prefix apps/client run build:weapp
```

当前业务页面仍由本地Python服务提供，不应将Vite开发服务器公开。S5实际审计和构建日志为.local/logs/s5-main-*；受控入口的框架API仍受固定Taro版本约束，不声称支持其全部CLI功能。依赖修复历史见[安全状态](SECURITY-BLOCKERS.md)，本轮结果见[验证记录](VALIDATION.md)。

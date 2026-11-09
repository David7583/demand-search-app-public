# 当前安全阻断项

状态：**既有桌面依赖修复已记录；本轮已授权独立公开源码；应用AGPL-3.0-only，原创文档CC BY 4.0。公开部署未授权，生产安全未验证，移动/微信工作暂停。** 本轮新的审计结果见[验证记录](VALIDATION.md)，不以历史记录替代。

S0于2026-11-04记录npm告警55项（low1、moderate29、high18、critical7），生产依赖6项（moderate2、high1、critical3）。原始审查和日志仅本地保存，不将后来修复倒写成S0已解决。

S1未更换Node锁；本轮S5在S2/S3检查点之后采用精确锁定修复，并以同版Taro service的受控构建入口替换不需要的CLI模板下载链，真正移除decompress、git-clone、download和doctor依赖。没有使用audit fix --force、关闭审计或隐藏devDependencies。

中间检查点为14项（low2、moderate9、high3、critical0），旧日志保留。随后实际迁移至 Vite6.4.5、static-copy2.3.2、html-minifier-terser7.2.0、glob14.0.3/minimatch11.0.4，并保留三个有来源和重建补丁的同名维护包。没有使用 force/legacy-peer-deps 或关闭完整审计。

此前桌面收口检查记录npm ci严格安装成功，完整/生产审计均0项、npm ls --all无无效依赖。原始证据在本地.local/logs/desktop-dependencies；这不是本轮新审计。三个维护包及224文件、实际Sass依赖路径已按该检查点核验，原MIT许可和来源保留。

既有桌面检查覆盖H5构建、Sass、静态复制/改名、越界拒绝、CORS/Host限制及合成浏览器回归。本轮成绩见[验证记录](VALIDATION.md)。旧告警作为历史保留；0公告不是无漏洞保证。自维护版本需继续按原上游名称/版本跟踪补丁，注册表可能无法识别全部修改。

未完成项包括hosted多用户安全、跨端身份、微信真机、后续公开范围变更审查；本次副本许可与范围已获授权。当前只做官方搜索入口，不宣称商品API接入。工程通过不能替代生产或公开发布条件。

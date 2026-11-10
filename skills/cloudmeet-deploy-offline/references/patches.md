# 补丁登记表（P01–P08）

这是离线包补丁内容的**唯一登记处**。每次打包由用户按入口、来源、架构和版本逐项选定，标"包含/不适用/待确认"，不是"全部自动应用"清单。"源文件"列是工作区相对路径，属于数据索引；路径变化只更新本表，不扩散到其他文档。

| ID | 补丁/配置 | 适用条件 | 源文件（工作区相对路径） | 持久化方式 | 必测 | 回滚 |
|---|---|---|---|---|---|---|
| P01 | 同源入口 | 需要 iframe DOM 访问且当前 origin 不一致时 | 业务 Web 构建配置（构建期 origin 变量，无独立工件） | 体现在构建产物中 | 实际 iframe origin、非本环境地址排查 | 回滚候选配置/产物 |
| P02 | 服务端品牌 | 当前 Jitsi 版本不接受相应 interface 覆盖时 | `deploy/patches/web/custom-interface_config.js` | Jitsi 持久 Web 配置，不要只改容器层 | 运行 interface_config 及会议视觉 | 恢复旧持久文件 |
| P03 | CSS 注入 | 需要本项目主题时 | `jitsi-meet-web/src/assets/custom.css`、`deploy/patches/web/custom-head.html`、`deploy/patches/web/nginx-custom/custom-css.conf` | 整套复制到持久 Web 配置；核对实际文件存在 | CSS hash/200、head 引用和真实页面 | 恢复整套旧文件 |
| P04 | JWT 主持人角色 | 使用当前项目主持人方案且镜像未包含时 | `jitsi-meet-cfg/prosody/prosody-plugins-custom/mod_muc_jwt_owner.lua` | Prosody 自定义模块持久目录，配置加载 muc_jwt_owner；配合 Jicofo 关闭 auto-owner | 实际模块加载、主持人 OWNER/普通 PARTICIPANT | 恢复旧模块与配置，窗口内重建受影响服务 |
| P05 | HTTP external_api | 用户批准 HTTP 测试且该版本硬编码 https 时 | `deploy/patches/optional-http/external_api.js`（先确认存在、来源及与上游版本相容） | 挂载到实际 serve 的 `libs/external_api.min.js`，不是根目录同名文件 | HTTP iframe 协议、入会 | 恢复原挂载/官方文件；HTTPS 且无需求时不应用 |
| P06 | HTTP 信令兼容 | HTTP 测试且模板会生成错误 wss/https 时 | 配置项 `BOSH_RELATIVE=1`、`ENABLE_XMPP_WEBSOCKET=0`（核对当前版本支持） | 持久配置而非手改运行文件 | 真实 BOSH 交互 | 回滚旧信令配置；HTTPS 正常 WebSocket 不照搬 |
| P07 | 客户端 HTTP/信任限定例外 | 明确测试且需要媒体，或内网私有 CA 信任时 | Electron 仅配置 origin 的 secure-context 例外；Android 仅批准主机的明文/信任策略（随客户端包） | 客户端构建配置，不进服务端镜像 | 指定 origin 媒体可用、其他 origin 未放宽 | 恢复配置并重打包（如需要）；不能全局关证书校验，新增主机要审核 |
| P08 | 老 WebView 语法 | 需支持现有 Android WebView 时 | 业务 Web 构建产物（经 `check:webview-syntax` 检查，构建记录随包） | 构建产物与检查记录 | 生成 JS 语法和真机 | 恢复旧前端候选 |

## 使用规则

1. **P04 不包含未经验收的 host-transfer 模块。** 存储 chown（storage 属主匹配镜像 uid/gid，基线 1000）、JWT 秘密一致、JVB 公网映射及端口选取属于条件配置修复，也要列入本次打包计划，不藏在后台执行。
2. **镜像路线**：先检查镜像内是否已含选中补丁，不重复注入、不猜文件布局；仅支持验证过的挂载/派生方式。
3. **版本变化后旧补丁不能自动套用**；逐项核对与本次版本的相容性，说明差异并暂停不兼容项。
4. 每个随包工件记录**真实 SHA256 与来源路径**到包的 manifest，不能伪造校验值。
5. 新补丁按"适用环境/版本、症状、证据、根因、最小修复、复验、回滚"登记进本表，分配新 ID。

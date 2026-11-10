# 202 单目标发布

> **既有实例记录，不是通用部署默认值。** 只有用户明确选择此既有实例、入口及来源，并核实服务器架构/实际挂载一致后才使用。本文件内IP、目录、端口和证书均为该实例快照，不可复制成新部署参数。先完成SKILL.md的域名/IP、源码/镜像、x86_64/ARM64询问和服务/补丁确认；实例脚本不支持任意目标。

## 权威依据与容易误读处

先读仓库 `jitsi-meet-web/AGENTS.md`、`deploy/publish-web-only.py`、`deploy/publish-api-only.py`；需要 Jitsi/入口操作再读 `docs/frp-relay/README.md`、`DOCKER_DEPLOY.md` 的 6.4/6.6/6.8。

- 业务容器预期 `jitsi-app-web`、`jitsi-app-api`；脚本均硬编码该既有实例，不能用于 ARM。
- Web live 为 `/opt/jitsi-app/web/dist`；API live 为 `/opt/jitsi-app/app/app.jar`。先 inspect 挂载确认，不把仓库根 Compose 当作服务器实际 Compose。
- 118 FRP 最终 HTTPS 转发至 202 的 **127.0.0.1:9443** 专用 Nginx，而非初装时的 443；旧 104/443 保留。FRP 控制 TLS 证书与浏览器叶证书不是同一张。
- 118 证书副本 `jitsi-meet-electron/src/certs/relay-118.pem`，当前文档有效期至 2027-10-22；发布时重新核实有效期及实际证书，不把旧摘要当永久事实。

## A. 只发布业务 Web（不重启容器）

1. 在 `jitsi-meet-web` 构建，清除/恢复会污染构建的进程级环境变量，不修改已批准 `.env`：

   ```powershell
   npm run build
   # 检查上一命令 $LASTEXITCODE 为 0 后才继续
   npm run check:webview-syntax
   Get-FileHash .\dist\index.html -Algorithm SHA256
   ```

2. 检查本次生成 JS 的有效 Jitsi URL：默认 118 发布拒绝内嵌 `https://192.168.199.202` iframe origin；检查 `/cm/assets/`、入口及实际懒加载文件。语法检查只证明 WebView 83 语法兼容，不是运行验收。
3. 读取远端 live `index.html` 的 SHA256 记为 OLD；本地 dist 的为 NEW。将 dist 打包上传至本次唯一 staging 目录，校验传输摘要并解包；不要直接 `scp -r dist/*` 覆盖 live，不删除旧 hashed assets。核对候选资源引用完整性，记录将覆盖/新增的非 hash 文件清单；确认只有一个发布者在执行，脚本没有并发发布锁。
4. 将当前仓库 `deploy/publish-web-only.py` 上传到 staging，审核后在服务器执行：

   ```bash
   python3 /path/to/staging/publish-web-only.py /path/to/staging/dist OLD_SHA256 NEW_SHA256
   ```

   `/path/to/staging` 和两个摘要须替换为本次值，不照抄占位符。脚本在开始时检查 live index 摘要、若干必要资源及新 index 摘要，不提供完整依赖校验或并发事务保障；备份至 `/opt/jitsi-app/backups/banner-web-<UTC>/`，先复制 assets，最后 `os.replace` 原子替换 index，保留旧 assets 并比较所有运行容器身份。
5. **不需要重启 Nginx/Web/API/Jitsi**。从 118 外网入口用受信任方式请求页面及新静态文件，比对摘要；在真实页面/Electron 检查页面与 iframe 同 origin、相关 UI 生效。

回滚：恢复脚本打印备份中的 `dist/index.html`，优先临时文件 + 原子替换；涉及其他非 hash 文件时按本次另记的变更清单从完整 dist 备份恢复；新增文件先确认无人使用再移除。脚本 manifest 只有 index 摘要和 staging 路径，并不包含完整文件清单。脚本异常仅自动恢复 index，不会自动撤销已覆盖的所有非 index 文件，不能声称“全量自动回滚”。不要清理仍可能被旧标签页引用的 assets。

## B. 只发布 API（只停启 API）

1. 在 `jitsi-meet-api` 本地执行 `mvn -B test package`，失败不上传。核实当前 pom/target 的真实主 JAR；当前文档为 `target/jitsi-meet-api-1.0.0.jar`，不能挑 sources/original/旧包。
2. 将新 JAR 以 `app.jar` 上传到本次独立 staging，脚本 `publish-api-only.py` 放**同一目录**；本地/远端 SHA256 一致后才执行。
3. 告知 API 短暂停机，确认窗口，再执行 `python3 /path/to/staging/publish-api-only.py`。
4. 脚本备份旧 JAR，`docker stop jitsi-app-api` 后备份 `/opt/jitsi-app/data/api`，复制新 JAR，finally 启动 API，检查其他容器未变。它**不自动校验上传摘要，也不做健康等待或自动回滚**，这些由执行者补齐。复制异常可能留下残缺 JAR，finally 启动不表示恢复；任何异常先核对 live 摘要并按已批准方案恢复旧 JAR。
5. 有截止时间地轮询 `/mapi/actuator/health`，看本次启动日志，再验证变更接口及一个无破坏性业务流程。API 恢复前不能报成功。

回滚：停 API，恢复备份 JAR，启动并验证。涉及 schema/data 变化先判断向后兼容；恢复数据须另外确认，会丢失备份后新增数据，不可自动覆盖数据库。

这里 JAR 是宿主 bind mount，不需套用低代码技能的镜像 build。若 inspect 显示已改为 COPY 镜像模式，停止沿用旧脚本，按实际镜像发布方案更新技能。

## C. 明确要求更新 Jitsi 时

- 先观察会议数/endpoints 并安排空闲窗口。不要顺带重启全栈。
- `/opt/docker-jitsi-meet` 的最终 Compose 镜像应使用官方基线；`deploy/docker-jitsi-meet/start-official-jitsi.sh` 会拒绝意外 override，但调用的是全栈 `up -d`，不是 Web-only 工具。
- 202 已占用端口：Jicofo REST `18888`、JVB Colibri `28080`；不要改回与低代码/SRS 冲突的默认 8888/8080/18080。
- JVB 首启端口冲突后可能残留无网络挂载/错误 resolv：确认无会议和根因后，仅 `--force-recreate jvb`；restart 不修复这种状态。

## D. 常见坑的最小修复

| 症状 | 核查与修复 |
|---|---|
| 新功能不见 | 核对本地/远端/公网 index 及新 JS hash，确认不是旧包/缓存；不要先重启全栈 |
| iframe DOM 被跨域拒绝 | 实际页面/iframe origin 比较；修复入口选择，不来回改 VITE 配置发包 |
| 水印未去除 | stable-11146 白名单会丢弃前端覆盖；在持久 Web 配置部署 custom-interface_config.js |
| custom.css 404/重建丢主题 | 同时部署 custom.css、custom-head.html、nginx-custom/custom-css.conf，走持久挂载而非改容器文件 |
| Prosody 重启 | 检查项目 storage/prosody uid/gid 1000:1000，只修项目目录权限 |
| 主持人 token 无效 | API JWT sub 对 docker-jitsi-meet 固定 meet.jitsi；app_id/secret 与 Prosody 一致，不输出秘密 |
| 人人是主持人 | 核对 enable-auto-owner=false、muc_jwt_owner 实际加载，真实验证 OWNER/PARTICIPANT；不擅自启用未验收 transfer 模块 |
| 入会但无媒体 | 核查官方 JVB、实际公网 advertise IP、UDP 10000 双向路径、ICE/媒体统计，不仅查端口监听 |
| 转发单向通/超时 | DNAT/SNAT/FORWARD 回程逐跳取证；118 FRP 与历史 104 ZeroTier 方案不同，不复制旧 iptables |

CentOS 旧实例的 trusted 网桥/firewall reload/删孤儿网桥做法只是历史特定修复，不是 202 Ubuntu 或 ARM 的部署步骤。

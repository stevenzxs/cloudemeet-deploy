# CloudMeet `11248-cm.20261110-rc2-amd64`

GHCR 七服务候选批次，仅 `linux/amd64`。`app-web` 基于 RC1 运行镜像替换静态资源，源码 `784c1d004cfcea32f5316314f5979cb74aba88b0`，修复主持人转移失败提示。网关、API、Jitsi Web、Prosody、Jicofo、JVB 复用 RC1 原摘要，不覆盖 RC1 标签。以 [registry.yaml](registry.yaml) 的七个 digest 为准，不要求七个仓库都有 RC2 标签。

## 下次拉取

在已有的 GHCR 兼容 Compose 中，用本目录的 `registry.yaml` 替换旧镜像锁定层。保留实例 env、网关配置、数据与 CA 卷，以及 `host-control/compose.json`。去掉旧 `host-control/web-compose.json` 中覆盖业务静态资源的挂载；确认没有其他 dist 或 nginx 配置挂载遮盖新镜像。API 保持镜像自带命令及 JAR，不恢复旧挂载。此文件不是根过渡模板的完整迁移方案。

用相同的 env、项目及 Compose 参数先执行 `config --quiet`，用 `config --images` 核对七项，再执行 `pull`；全部通过后才能按维护窗口切换。`pull` 不会替换运行中的容器。

## 主持人转移的外置配置

镜像锁不包含实例生成的私有 TLS、密钥或运行配置。按 [主持人转移手册](../../patches/prosody/HOST-TRANSFER.md) 保留或生成这些配置，核对公开补丁的 SHA256：

| 文件（相对部署仓库） | SHA256 |
|---|---|
| `patches/prosody/mod_muc_host_transfer.lua` | `91779945f43d4f7d7ad2cabe32f04503fb62d29ddaf410e74cfc87209b1b201c` |
| `patches/prosody/mod_muc_jwt_owner.lua` | `487d662613d47c1a2d7b52e367946614bc2e975ae0d5ea74aa25b1a04620ee9d` |
| `patches/web/host-control-custom-config.js` | `165c9ef588096ab31e528ffbdc9171fee1df7b3e742a46ac717c5eb5ffe93ca3` |

## 验证和回滚

业务 Web `npm run verify` 通过（231 个测试、11 个 WebView JS 资源语法检查），镜像内新版 MeetingStage JS SHA256 为 `d066b494fa8ad3b239635a11f6f36141f731b219c51c046519abb5b345f94344`。七项按 digest 在本机 Docker 拉取及架构核对通过，使用了已有缓存；未进行空缓存、目标实装、RC2 转移/撤权/重连或媒体联合验收。RC1 的已知风险不因这次发布而消除。

若仅新版业务 Web 回归失败，用旧锁定层及对应 Web 配置回退 `app-web`，保留当前数据库、角色撤权、TLS 和 CA 配置。已发生转移或有未完成操作时，不关闭在线撤权、不还原旧 SQLite。

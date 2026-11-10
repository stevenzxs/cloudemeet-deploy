# 镜像与工件清单（核对基线，非内容默认）

这是当前基线的**核对快照**，用于打包时查漏。每次打包必须以本次渲染的 Compose 为准重新枚举；版本升级后本表需更新，不得把本表当内容默认照搬。本表与 `patches.md` 是本技能仅有的两个工作区来源路径索引，其他章节不直接出现工作区路径。

本表最后核对日期：2026-11-07（对应 jitsi 基线 stable-11146-2）。

## 1. 基线镜像（全栈七服务）

| 逻辑服务 | 基线镜像 | 架构支持 | 大小量级（压缩前） | 核对要点 |
|---|---|---|---|---|
| jitsi-web | `ghcr.io/jitsi/web:stable-11146-2` | 官方多架构（以 manifest 实际为准） | ~300MB | PUBLIC_URL、品牌补丁工件挂载 |
| prosody | `ghcr.io/jitsi/prosody:stable-11146-2` | 同上 | ~100MB | P04 角色插件挂载、storage 属主（uid/gid 1000） |
| jicofo | `ghcr.io/jitsi/jicofo:stable-11146-2` | 同上 | ~300MB | auto-owner 关闭与 P04 配套 |
| jvb | `ghcr.io/jitsi/jvb:stable-11146-2` | 同上 | ~400MB | **架构错配最高发**；advertise 地址安装时配置 |
| gateway | `caddy:2.10.2-alpine` | 官方多架构 | ~50MB | 需 DNS 插件时必须用插件版构建，不能用标准镜像冒充 |
| app-web | `nginx:1.27-alpine`（承载业务静态产物） | 官方多架构 | ~50MB | 业务产物 bind-mount 还是派生镜像，按本次方案 |
| api | `eclipse-temurin:17-jre`（承载业务 JAR） | 官方多架构 | ~250MB | JAR 挂载更新策略；SQLite 持久化 |

注意：历史上出现过 `cloudmeet/*:source-*` 自构建候选镜像记录，说明存在源码自构建路线产物；自构建镜像的架构支持以**实际构建记录**为准，不能因官方镜像多架构就推定业务镜像多架构。业务镜像是否已发布到可拉取仓库须向用户确认，不编造仓库地址。

## 2. 补丁工件

补丁内容、源文件路径、适用条件、必测与回滚统一见 [补丁登记表](patches.md)（同一目录），本表不再重复登记。打包时按登记表逐项核对存在性与摘要，写入 manifest。

## 3. 客户端包（可选）

| 工件 | 构建方式 | 随包核对 |
|---|---|---|
| Electron MSI | 工作区 `build-tools/clients/build-clients.cjs` + 客户端专用 env（SITE_DOMAIN/SITE_SCHEME/SITE_PORT）；批次 `deploy/history/client-builds/`，验收后交付 `deploy/clients/` | 入口 origin 与本次证书方案一致；信任模式（内嵌根/安装导入）已确认；SHA256 |
| Android APK | 同上 | 明文/信任策略仅限批准主机（P07）；SHA256 |

客户端信任的是**目标机安装时生成的私有 CA 根**——若客户端包内嵌 CA 根，则客户端必须在目标机 CA 确定之后构建或更新；打包顺序与信任一致性在安装手册中写明。

## 4. 规模估算与介质

全栈七镜像压缩后约 1.5–2GB（zstd），加客户端约 2–2.5GB；单张 DVD 或 4GB FAT32 U 盘需分卷。估算仅供介质准备，实际以当次产出为准并在 REPORT.txt 记录真实大小。

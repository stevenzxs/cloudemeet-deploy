---
name: cloudmeet-server-build-deploy
description: Use when the user requests a standalone CloudMeet server-side (eight services) container build and/or GHCR+Release publication, without the joint workflow. Triggers on "构建服务端/构建八个服务/构建镜像/发布服务端/服务器打包发布/单独构建服务端". Covers the minimal workflow build-server.yml (version → build → publish). Not for joint full delivery (full-build-deploy), patch hotfix (single-build-deploy), client builds (android/msi-build-deploy), or any server deployment.
---

# CloudMeet 八个服务端服务独立构建与发布

本技能只覆盖服务端八个服务的独立构建与发布，使用最小工作流 `.github/workflows/build-server.yml`（version → build → publish 三个 job，结构与 msi/android 技能一致）。它是操作步骤，不构成额外授权；只执行用户明确要求的终点。

范围：七个容器镜像 `gateway`、`app-web`、`api`、`web`、`prosody`、`jicofo`、`jvb`（GHCR）+ `jitsi-mgr` 后端 JAR 与管理前端静态产物（由网关托管，非容器）。**不在范围**：H5 资产、安装包组装（compose 渲染/在线安装材料）、客户端、部署与升级。联合批次走 `skills/full-build-deploy`，patch 热修复走 `skills/single-build-deploy`。

## 任务终点与授权

- “检查、预检、仅构建”：只读核验或构建（`publish_images=false`），不推 GHCR、不建 Release。
- “构建并发布”：用户明确授权本批发布时才设 `publish_images=true`；推送镜像到 GHCR 并创建 Release。发布不包含任何目标服务器操作。
- 本技能没有部署终点。安装、TLS、会议媒体验收不在范围，证据统一标注 `NOT_DEPLOYED`。

## 版本规则

- 修订号 `rN` 由共享分配器 `.github/workflows/revision-allocation.yml`（scope `["server"]`）分配并写入主分支台账；台账活数据为 `full-build-deploy/config/version-policy.json`，只读引用、不拷贝、不手填、不回收编号。失败或取消同样消耗编号。
- 服务端版本：`server_version = 11248.0.1+rN`，`server_tag = 11248.0.1-rN`；镜像 tag 与 Release tag 为 `<server_tag>-<run_id>-<attempt>`。

## 固定契约（不得在本任务中更换）

- 源码：`sources.json` 的八个服务及 lifecycle（docker-jitsi-meet rootfs），与 workflow 检出 commit 三方一致（构建前断言 checkout == sources.json）。
- 镜像命名：`ghcr.io/stevenzxs/cloudmeet-<service>:<server_tag>-<run_id>-<attempt>`；发布记录以 digest 固定引用（`images.json`）。
- Release 命名：`cloudmeet-<server_tag>-<run_id>-<attempt>`，与既有联合 Release 序列同规。
- 基础镜像按 Dockerfile 内 digest 固定引用；构建器镜像（node/golang/temurin）为构建环境，不进入交付身份。

## 构建入口（GitHub Actions `build-server.yml`）

1. 核对配置仓库分支与工作区干净后同步 `origin/main`；记录实际 `material_commit`（完整 SHA，必须等于 workflow 提交）。
2. `workflow_dispatch` 输入：`expected_tls_mode`（默认 `private-ca`）、`expected_origin`、`material_commit`、`architecture`（默认 `amd64`）、`publish_images`。
3. `version` job：复用共享分配器，输出 assignment 与 origin 契约。
4. `build` job（按架构原生 runner，八服务矩阵）：检出 deploy@material_commit 与对应源码@固定 commit → `tools/build-service.sh <service>` 完成编译、`docker build`（web/app-web/api/gateway/prosody/jicofo/jvb）或 jitsi-mgr 产物（JAR + 前端）→ `docker save` tar.gz + `build-evidence.json` → artifact 保留 14 天。
5. `publish` job（仅授权）：下载同一 Run/attempt 全部 artifact → 逐服务校验 tar.gz 摘要 == 证据 → `docker load` → tag/push GHCR → 记录 digest 生成 `images.json` → 组 release 目录（images.json、jitsi-mgr.jar、jitsi-mgr-ui.tar.gz、各服务 build-evidence.json、SHA256SUMS）→ `gh release create --draft`（**不带资产**）→ `gh release upload` 同步上传（退出码即权威校验）→ `gh release edit --draft=false` 公开。

## Release 资产（v1 最小集）

- `images.json`：七服务 GHCR digest 固定引用、批次、Run/attempt、部署提交，状态 `PUBLISHED_NOT_DEPLOYED`。
- `jitsi-mgr.jar`、`jitsi-mgr-ui.tar.gz`：jitsi-mgr 后端与前端产物。
- `<service>-build-evidence.json` × 8：各服务构建证据（源码 commit、镜像 ID/产物摘要、架构）。
- `SHA256SUMS`：上述全部资产摘要。

部署/升级如何消费本 Release 由部署侧另行适配；本技能不产出 compose 安装包。

## 已知陷阱（与 MSI 链路共享的实测教训）

- **publish job 不 checkout 仓库**：`gh release *` 需要 `GH_REPO` 环境变量（r55 失败点）。
- **GitHub 资产列表可见性延迟 2–6+ 分钟**：禁止资产计数轮询；`gh release upload` 同步退出码才是权威判据（r56–r58 失败点，r59 实证修复）。
- **失败即消耗 rN，不回收**：修复材料后必须新 Run/新编号。
- **bash 单引号不展开变量**：`'$GITHUB_SHA'` 是字面字符串，材料一致性断言恒失败（r61 失败点）；shell 变量引用必须双引号（测试已钉住）。
- **`fromJSON` 只解析 JSON**：commit SHA 以数字开头时 `fromJSON('2768…')` 按数字解析报模板无效（r62 失败点）；固定 ref 直接写字面量，测试钉住与 sources.json 一致。
- **Maven Central 限流 CI（429）**：`api`/`jicofo`/`jvb`/`jitsi-mgr` 构建必须经腾讯云镜像路由（settings.xml mirrorOf=central），直连 Central 会被 429 拖死（r62 api 失败点）。

## 必须停止并报告的情形

- material_commit 与 workflow/检出提交不一致；源码 checkout 与 `sources.json` pin 不一致。
- 构建任一步骤失败（编译、lua 依赖摘要、Dockerfile 构建、镜像架构不符）。
- 发布前 tar.gz 摘要与证据不符；GHCR push 失败；Release 上传失败。
- 请求超出“构建+发布”终点（部署、升级、H5、安装包组装、证书切换）。

停止时说明已完成的最后阶段、精确失败项、保全的证据位置和仍未执行的阶段；不自行扩大修复范围。

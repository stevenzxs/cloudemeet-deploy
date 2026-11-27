# Skill: single-build-deploy

# CloudMeet 单服务/单客户端 patch 构建与发布

本技能覆盖"单个目标源码小改动"的热修复交付：以某个**已发布**的 joint 批次为基础，只构建并发布变更的那一件（八个服务端服务之一，或 electron，或 android）。它是操作步骤，不构成额外授权；不得因本技能被调用而推定用户已授权发布、部署或任何破坏性操作。只执行用户明确要求的终点。

设计依据：`docs/superpowers/specs/2026-11-27-single-build-deploy-design.md`。

## 与联合交付的边界

- 不分配新 rN、不消耗 joint 修订号；版本身份为 `<基线>+r<base_revision>-patch.<N>`。
- 不组完整离线包、不出 H5 资产、不出线上安装材料。
- 不替换、不覆盖、不删除任何既有 Release 资产、GHCR tag 或版本记录；全部产物以新名字新增。
- 不部署、不连接目标服务器；发布完成不等于安装、TLS 或媒体验收。

## 版本与编号规则

- patch 编号 N 取值 1..9，由 `tools/patch_release.py` 只读枚举既有 Release/tag 推导 max+1；禁止手填、猜测、回收。
- 客户端数字版本（与 full-build-deploy 同一公式）：`android_code = base×1000 + rN×10 + patch`，`msi = major.minor.((client_patch+rN)×10 + patch)`，PE 追加 `.0`。示例：基线 1.0.21、r45-patch.1 → `1021451` / `1.0.661` / `1.0.661.0`。
- 服务端 tag：`11248.0.1-r45-patch.1`；Release 名：`cloudmeet-11248.0.1-r45-patch.1`。
- patch 记录为平行 schema（`kind: "patch"`，含 `request.target`），只由 `tools/patch_release.py` 生成与校验；joint 分配器与校验器不读它。

## 任务终点与授权

- "检查、预检、仅构建"：只读核验或构建，不发布。
- "构建并发布"：仅当用户明确授权本批发布（`publish_images=true`）时才执行发布 job；发布不包含任何目标服务器操作。
- 本技能没有部署终点。部署请求一律停止并转交既有升级路径。

## 前置条件（缺一即停）

- hotfix 源码 commit 已合入对应源码仓库，并已更新 deploy 仓库 `sources.json` 中该目标的条目；该提交即 `material_commit`。
- 基础批次发布证据存在：非 draft 的 `cloudmeet-<server_baseline>-r<base>-*` Release；服务端目标另需 GHCR 基础 tag 可解析 digest；客户端目标另需该 Release 含对应类型资产（`.msi`/`.apk`）。
- `base_revision` ≤ `version-policy.json` 的 `current_revision`。

## 执行（GitHub Actions `build-single.yml`）

1. 核对配置仓库身份、分支、工作区干净、无在途任务后同步 `origin/main`；记录实际 material commit。
2. `workflow_dispatch` 输入：`base_revision`、`target`、`expected_tls_mode`、`expected_origin`、`material_commit`、`architecture`（仅服务端）、`publish_images`。
3. `version` job：校验材料与 origin 契约 → `check-base` 基础发布证据 → `allocate` 推导 patch 号并生成 patch 记录。同 base+target 的并发由 workflow concurrency 组串行化。
4. `build` job：服务端复用 `skills/full-build-deploy/scripts/package.sh build <target>`；客户端复用 `tools/clients/build-clients.cjs`（源码 commit 从 `sources.json` 动态检出，并断言检出 == sources.json == patch 记录三方一致）。
5. `publish` job（仅授权时）：服务端推 GHCR 新 tag（已存在即停）并建独立 Release；客户端只建 Release（MSI/APK + 证据 + SHA256SUMS）。Release 先 draft 核验再公开，`--latest=false`，证据标注 `NOT_DEPLOYED`。
6. 保存 Run URL/ID、patch 记录、镜像 digest、Release 与资产摘要；不表述为部署或验收通过。

## 必须停止并报告的情形

- base_revision 超过 current_revision，或基础批次发布证据缺失。
- patch 编号推导发现撞号，或目标 GHCR tag / Release 已存在。
- hotfix commit 未固定进 `sources.json` 的受审提交；material_commit 与工作流提交不一致。
- origin 契约、TLS 模式、架构与批准输入不符。
- 构建/发布校验任何一项失败；出现任何覆盖、删除、替换既有产物的需要。
- 请求超出"构建+发布"终点（如部署、升级、证书切换）。

停止时说明已完成的最后阶段、精确失败项、保全的证据位置和仍未执行的阶段；不自行扩大修复范围。

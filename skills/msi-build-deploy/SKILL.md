---
name: cloudmeet-msi-build-deploy
description: Use when the user requests a standalone CloudMeet Windows client (Electron MSI) build and/or GitHub Release publication, without the joint eight-service delivery. Triggers on "构建 MSI/Windows 安装包/Electron 打包发布/单独构建 MSI/发布 MSI". Covers the minimal workflow build-msi.yml (version → build → publish). Not for joint full delivery (full-build-deploy), patch hotfix (single-build-deploy), or any server deployment.
---

# CloudMeet Windows MSI 客户端独立构建与发布

本技能只覆盖 Electron Windows MSI 的独立构建与发布，使用最小工作流 `.github/workflows/build-msi.yml`（version → build → publish 三个 job）。它是操作步骤，不构成额外授权；只执行用户明确要求的终点。联合批次走 `skills/full-build-deploy`，patch 热修复走 `skills/single-build-deploy`。

## 任务终点与授权

- “检查、预检、仅构建”：只读核验或构建（`publish_images=false`），不发布。
- “构建并发布”：用户明确授权本批发布时才设 `publish_images=true` 执行 publish job；发布不包含任何目标服务器操作。
- 本技能没有部署终点。MSI 安装/升级/卸载、线上 TLS 与会议媒体验收不在范围，证据统一标注 `NOT_DEPLOYED`。

## 版本规则

- 修订号 `rN` 由共享分配器 `.github/workflows/revision-allocation.yml`（scope `["electron"]`）分配并写入主分支台账；台账活数据为 `full-build-deploy/config/version-policy.json`，只读引用、不拷贝、不手填、不回收编号。失败或取消同样消耗编号。
- 数字版本（公式 2）：显示 `1.0.21+rN`，MSI 第三段 `(client 基线 patch + rN)×10`（如 r45 → `1.0.660`），PE 版本追加 `.0`；末位 1..9 预留给 single-build-deploy 的 patch 发布。
- 单独构建 MSI 会让 Android 跳过对应 rN 段，不影响单调性。

## 固定契约（不得在本任务中更换）

- 源码：`sources.json` 的 `clients.electron`（jitsi-meet-electron），与 workflow 中硬编码 `ref` 必须一致（tests/test_msi_workflow.py 钉死）。
- 签名（2026-11-20 用户批准）：Windows EXE/MSI **不执行代码签名**，不要求 PFX、SignTool、私有证书库或时间戳；交付记录 `signing: {required:false,status:"unsigned"}`，README/Release notes 明确 UNSIGNED 及未知发布者/SmartScreen 风险。历史 Windows 签名工具/身份/Secrets 保留但不用于本入口。
- 快捷方式：MSI `Shortcut` 表必须含桌面与开始菜单两项中文长名称“云会议”且主程序目标为 `cloudmeet.exe`，英文/缺项/重复/错误目标立即失败（验包内置）。
- CA 信任：`config/client-ca.crt`（DER SHA256 `fab880721274fa86d6a23d8f00fb93be471af863bec0fced6b7e99780b5e6fde`），打入 client-trust.json/client-ca.crt 严格校验。
- TLS 模式为 dispatch 输入（默认 `private-ca`），`private-ca` / `caddy-public-acme` 两种批准模式均可；模式与 origin 契约绑定同一批次，模式切换属受控变更，不是普通构建参数。

## 构建入口（GitHub Actions `build-msi.yml`）

1. 核对配置仓库分支与工作区干净后同步 `origin/main`；记录实际 `material_commit`（完整 SHA，必须等于 workflow 提交）。
2. `workflow_dispatch` 输入：`expected_tls_mode`（默认 `private-ca`）、`expected_origin`、`material_commit`、`publish_images`。
3. `version` job：复用共享分配器，输出 assignment 与 origin 契约（含 DNS 证据）。
4. `build` job（windows-2022）：检出 deploy@material_commit 与 jitsi-meet-electron@固定 commit → 写批次 env/origin 契约 → WiX v3 前置检查 → `npm ci` → `node deploy/skills/msi-build-deploy/tools/clients/build-clients.cjs --target electron --env-file batch-client.env --origin-contract batch-origin.json --version-record version-assignment.json`。构建器经 Forge + maker-wix 产出 MSI，验包（管理解包核对版本、PE 架构 x64、入口/CA、unsigned 记录、中文快捷方式）后交付 `deploy/release/clients/windows/x64/<批次>/`，artifact 保留 14 天。
5. `publish` job（仅授权）：下载同一 Run/attempt artifact → 定位 `<client_version>-cloudmeet-clients-*` 交付目录 → `sha256sum -c SHA256SUMS` → `gh release create --draft`（`--latest=false`，notes 标 UNSIGNED 与 `NOT_DEPLOYED`，**不带资产**）→ `gh release upload` 同步上传 MSI + build-evidence.json + SHA256SUMS（同步退出码即权威校验）→ `gh release edit --draft=false` 公开。

## 本地构建（可选，Windows 工作区根，需 WiX v3）

```powershell
# 只读预检（不分配版本，报告诊断基线与缺项）
node deploy/skills/msi-build-deploy/tools/clients/build-clients.cjs --target electron --env-file "$PWD/deploy/skills/msi-build-deploy/config/client.env" --check
```

正式构建必须携带 `--version-record`（分配记录），不得绕过统一入口直接跑 Forge/npm make 充当正式发布。本机 PATH 已有 `D:\tool\wix311-binaries`（v3.11.2），无需重复安装。工具细节见 `tools/clients/README.md`（与 Android 技能共用同一构建器，README 同时覆盖两端）。

## 防漂移约定

`tools/clients/` 与 `config/` 是 `full-build-deploy` 同名内容的自包含副本（2026-11-27 拆分）。副本必须与维护源保持一致；`tests/test_tool_parity.py` 钉死逐文件一致，改任一侧须同步另一侧并重跑测试。唯一允许的跨技能依赖是活数据 `version-policy.json`（不拷贝）。

## 已知陷阱（本链路 r55–r59 实测教训，publish 三连失败的根因）

- **publish job 不 checkout 仓库**：`gh release *` 需要 `GH_REPO` 环境变量解析目标仓库，否则报 `fatal: not a git repository`（r55 失败点，`31b0f12` 修复并钉测试）。
- **GitHub 资产列表可见性延迟 2–6+ 分钟且不稳定**：资产在 create 时即已上传，但 `gh release view` 计数迟迟只见 1 个；任何固定窗口的计数轮询都不可靠（r56–r58 连续失败点）。禁止用资产计数/列表查询作为上传成功判据——`gh release upload` 的同步退出码才是权威判据（`8b1c789` 结构性修复，r59 一次跑通实证）。
- **`/releases/latest` 徽章不可控**：本仓库所有 release 的 `make_latest` 均为 null，徽章按创建时间自动归属最新非 draft release；最新客户端 release 会暂时占据徽章，下次 joint 发布自动夺回，不做额外治理。
- **失败即消耗 rN，不回收**：修复材料后必须新 Run/新编号（r55–r58 已按此规则消耗）。

## 必须停止并报告的情形

- material_commit 与 workflow/检出提交不一致，或 origin 契约、TLS 模式与批准输入不符。
- 源码 checkout 与 `sources.json` pin 不一致；分配记录缺失或版本重算不符。
- WiX v3 不可用、CA 证书缺失/过期/指纹不符；验包任何必需项失败（含中文快捷方式核验）。
- 构建/验包任何必需项失败；目标 Release tag 已存在或发布后资产数不符。
- 请求超出“构建+发布”终点（部署、升级、证书信任迁移、恢复 Windows 签名等身份变更）。

停止时说明已完成的最后阶段、精确失败项、保全的证据位置和仍未执行的阶段；不自行扩大修复范围。

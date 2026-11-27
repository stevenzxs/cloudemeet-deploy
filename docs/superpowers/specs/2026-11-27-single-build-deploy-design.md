# Single Build Deploy 设计：单服务/单客户端 patch 构建发布

日期：2026-11-27
状态：待批准

## 意图与为什么

CloudMeet 联合交付（`build-joint.yml`）每次分配新 rN、构建全部八个服务加两个客户端，对"单个服务源码小改动"的热修复过重。本设计新增 `single-build-deploy` 技能：以某个已发布 joint 批次为基础，只构建并发布变更的那一件（一个服务端服务或一个客户端），**不升级版本**（不分配新 rN），**不替换原发布包**，以 patch 后缀的新身份**新增发布**。

## Goals

- 单个目标（八个服务端服务之一，或 electron，或 android）的独立 patch 构建与发布。
- 版本身份 `<base>+r<base_revision>-patch.<N>`，N 只读推导，不手填。
- 新建独立 GitHub Release；GHCR 使用新 tag；任何既有 Release 资产、镜像 tag、台账记录不被修改或覆盖。
- 证据链与 joint 同标准：同一 Run/attempt、material_commit、origin 契约、固定源码 commit、版本记录绑定。
- 用户显式授权本批发布时才执行发布 job。

## Non-goals

- 不部署、不升级目标服务器（终点 = 构建 + 发布）。
- 不组完整离线包（不跑 `package.sh assemble`），不产出 H5 资产、服务端整包 tar.gz、在线安装材料。
- 不修改客户端签名身份、TLS 模式、CA 信任材料。
- 不做版本回收、patch 编号复用、多目标同批构建。

## Anti-goals

- patch 产物与任何既有产物同名（防覆盖）。
- 无版本记录的构建；patch 编号手工输入。
- 把 patch 构建伪装成 joint 批次（身份必须显式含 `patch.N`）。

## 约束

- Android `versionCode` 为递增整数且 ≤ 2.1e9；MSI ProductVersion 为三段数字且每段 ≤255/255/65535；PE 四段。
- patch 版本必须大于基础批次版本、小于下一个 joint 版本，否则原地升级链路断裂。
- 已发布 joint 版本（android_code ≤ 102145、MSI ≤ 1.0.66）不可变。
- patch 编号 N 每 base_revision 取 1..9（×10 预留位方案的限制）。
- origin 契约、TLS 模式、架构校验与 joint 完全一致；构建/发布阶段不访问目标 origin。

## Approaches

- **A（选定）：×10 预留 patch 位，joint 与 patch 共用新公式。** 有界修改 `full-build-deploy` 的版本公式实现。理由见下。
- B（否决）：v1 只支持服务端。服务端 tag 是纯字符串、零公式改动，但用户要求客户端方案一起定；且 patch 坑位必须在 joint 公式里预留，拖到以后改会让中间发布的 joint 版本把坑位挤没。
- C（否决）：joint 公式不动、patch 独立编码。joint r46 旧公式为 102146，小于 patch 1021451，joint 升级变降级；要让 joint 跳过已用 code 又得让分配器感知 patch 记录，耦合更隐蔽。
- 发布形态：**新建独立 patch Release（选定）**；追加资产到原 Release（否决：原批次资产清单被改变，违反"不动原发布包"）。
- patch N 来源：**`gh` 只读列出现有 release/tag 取 max+1（选定）**；台账文件（否决：多一处真相源）；手填（否决）。

## 版本方案（选定的 A）

同一套新公式同时用于今后的 joint 与 patch，保证全局单调：

| 项 | 新公式 | r45-patch.1 | 下一 joint r46 | 已发布旧值 |
|---|---|---|---|---|
| Android versionCode | `base×1000 + rN×10 + patchN`（joint 时 patchN=0） | 1021451 | 1021460 | ≤102145 ✓ 更小 |
| MSI ProductVersion | `major.minor.((client_patch+rN)×10 + patchN)` | 1.0.661 | 1.0.670 | 1.0.66 ✓ 更小 |
| PE 版本 | MSI + `.0` | 1.0.661.0 | 1.0.670.0 | 1.0.66.0 |
| 服务端 tag | `<server_baseline>-r<N>-patch.<P>` | 11248.0.1-r45-patch.1 | 11248.0.1-r46 | 11248.0.1-r45 |
| 显示版本 | `<client_baseline>+r<N>-patch.<P>` | 1.0.21+r45-patch.1 | 1.0.21+r46 | 1.0.21+r45 |

- base=1021、client_patch=21 来自 `version-policy.json` 的 `android_base_code`/`client_baseline`。
- 切换安全：新公式最小 joint 值（1021010 / 1.0.660）已大于全部已发布旧值；`previous_android_code` 下限校验继续通过。
- 公式变更只影响新 Run 产生的新记录：分配器仅在分配**新** revision 时调用 `derive()`，`validate_record` 只重算**本 Run** 的新记录；旧 Run 重试按 material_commit 检出旧代码、用旧公式，自洽。
- 新分配记录与 patch 记录增加 `version_formula: 2` 字段作为纯审计标记（不做分支逻辑；公式由代码版本决定）。——设计者定的小决定。

## 对 full-build-deploy 的有界修改

| 文件 | 修改 |
|---|---|
| `tools/revision_versions.py` | `derive()` 改用新公式；新记录写入 `version_formula: 2` |
| `tools/clients/core.cjs` | `versionCode()` 改用新公式并解析 `+rN-patch.N` 后缀；`parseConfig` 的 assignment 校验按新公式重算 |
| `tools/clients/revision-config.cjs` | `loadAssignment()` 接受 patch 记录（绑定校验不变，版本重算走新公式） |
| `scripts/package.sh` | `VERSION` 正则允许可选 `-patch.N` 后缀（`BATCH` 模式已兼容）；其余不动 |
| 测试 | `core.test.cjs`、`revision.test.cjs`、`cli.test.cjs`、`test_revision_versions.py` 等钉死旧公式数值的断言更新；新增 patch 公式用例 |
| `tools/clients/README.md` | "Android versionCode自动转换" 一节同步新公式 |
| `SKILL.md` | 补一句版本规则说明（公式细节指向本设计） |
| `deploy/README.md` | 客户端构建入口指向从 `build-tools/` 改为 `skills/full-build-deploy/`（builder check Q3，设计者定） |

**`build-tools/` 的处置（builder check Q3，设计者定）**：冻结为 legacy，公式**不**镜像过去。依据：`.githooks/pre-commit` 已不再强制维护其 `inputs.sha256`；`test_workflow_isolation.py` 断言所有 workflow 不得引用 `build-tools/`；迁移 STATUS 文档表明技能目录是继承者。唯一风险是 `deploy/README.md` 仍把 build-tools 写成客户端构建入口——按上表改指向消除分歧。

**完整性门禁（builder check Q5，设计者定）**：`build-tools/inputs.sha256` 已停止维护（pre-commit 注明），新增 workflow/技能目录无需更新任何哈希清单；`test_workflow_isolation.py` 只断言既有四个 workflow 的性质，新增 `build-single.yml` 不破坏它们，但要在 `single-build-deploy/tests/` 为新 workflow 补等价结构测试。实施时以全量仓库测试通过为准。

不动：`docker/`、`runtime/`、四个既有 workflow 结构、`joint-release.py` 发布机制、`config/` 下 CA/签名材料。

## patch 身份与编号

- 工作流输入 `base_revision`（整数，≤ `version-policy.json` 的 `current_revision`）。
- patch N：发布前用 `gh release list`/`gh api` 只读枚举匹配 `cloudmeet-<server_baseline>-r<base_revision>-patch.*` 的 tag，取 max+1；无匹配则 N=1。workflow 对该 base 设 `concurrency` 组防并发推导撞号；推送/建 Release 前再查一次，已存在即停。
- patch 版本记录（`patch-assignment.json`）：namespace 沿用 `cloudmeet-joint-v1`；`request` 绑定 repository、workflow、run_id、configuration_sha（=material_commit）、hotfix 目标与源码 commit、base_revision、patch、scope=[该目标]；`versions` 同 joint 结构并含 `patch`、`version_formula: 2`；`allocation_sha256` 自校验。生成即落 evidence。

## 源码治理

- hotfix 服务的新 commit 先合入对应源码仓库，并更新 deploy 仓库 `sources.json` 中该服务的 commit（此提交即 `material_commit`，走正常受审流程）。
- 其余服务的 sources.json 条目不动、不重新构建；patch 记录携带全量 sources（与 material_commit 的 sources.json 一致），`package.sh` 的全量来源校验保持不变。
- **客户端源码固定方式（builder check Q1，设计者定）**：joint 流程靠 workflow 文件里硬编码 `ref:` 固定客户端源码；patch 流程的 commit 每次变，改为**动态检出 + 双向断言**：`build-single.yml` 从 `sources.json@material_commit` 读出该目标的 commit 并检出，随后断言 `git rev-parse HEAD` == sources.json 条目 == patch 记录 `request.sources` 条目。绑定强度与 joint 硬编码等价（两者都是 material_commit 里的受审仓库内容）。不允许把 commit 做成 workflow 自由输入。

## patch 记录与 joint 校验器的关系（builder check Q2，设计者定）

- patch 记录是**平行 schema**，只由 `single-build-deploy/tools/patch_release.py` 生成和校验；joint 的 `validate_request`/`validate_record` 不扩展、也永远不会读到 patch 记录。
- `request.scope` 复用 joint 粗粒度词汇（服务端 patch 用 `"server"`，客户端用 `"electron"`/`"android"`）；具体目标身份放独立的 `request.target` 字段（八服务之一 | electron | android）。
- 记录增加 `kind: "patch"` 与 `versions.patch`，与 joint 记录明确区分。
- `patch_release.py` 自行重算版本（新公式 + patch 参数）并校验 `allocation_sha256`。

## 基础批次发布证据的判定（builder check Q4，设计者定）

patch 前必须只读核验基础批次已发布，缺一即停：

- 存在**非 draft** 的 GitHub Release，tag 匹配 `cloudmeet-<server_baseline>-r<base_revision>-*`（joint tag 带 run/attempt 后缀，故为前缀匹配）。
- 服务端目标：GHCR 上该服务的 `cloudmeet-<service>:<server_baseline>-r<base_revision>` tag 可解析出 digest。
- 客户端目标：该 Release 资产清单中包含对应类型资产（electron → `.msi`，android → `.apk`）。
- 仅在 `version-policy.json` 里分配过但未发布，不构成基础。

## 构建

- 服务端（含 jitsi-mgr 的 JAR+前端形态）：复用 `skills/full-build-deploy/scripts/package.sh build <service>`；`VERSION=<server_baseline>+r<base>-patch.<N>`，`VERSION_RECORD` 指向 patch-assignment.json。架构输入 `amd64|arm64` 同 joint。
- 客户端：复用 `tools/clients/build-clients.cjs`；批次 env 的 `CLIENT_VERSION=<client_baseline>+r<base>-patch.<N>`；MSI/APK 版本注入走既有 forgeWrapper/gradle 参数，吃记录里的 `versions`。
- 预检、网络审计、证据文件、`NOT_RUN_PACKAGING_ONLY` 语义全部沿用。

## 发布（仅当本批显式授权 `publish_images=true`）

- 新建 GitHub Release `cloudmeet-<server_baseline>-r<base>-patch.<N>`（draft→核验→公开，`--latest=false`）：
  - 服务端：该服务镜像 tar.gz + 构建证据 JSON + SHA256SUMS。
  - 客户端：MSI 或 APK + 构建证据 + SHA256SUMS。
  - Release 正文/证据明确 `NOT_DEPLOYED`。
- 服务端镜像推 GHCR：`ghcr.io/stevenzxs/cloudmeet-<service>:<server_tag>-patch.<N>`；推送前查询 tag 已存在即停止；发布记录使用 digest 固定引用。
- 不触碰任何 joint Release、`cloudmeet-<service>:<server_tag>-r<N>` 原 tag、MSI/APK 原资产。

## 工作流

新增 `.github/workflows/build-single.yml`（`workflow_dispatch`）：

- inputs：`base_revision`、`target`（八服务之一 | electron | android 单选）、`expected_tls_mode`、`expected_origin`、`material_commit`、`architecture`（仅服务端）、`publish_images`（默认 false）。
- job 链：patch 版本推导与记录生成（复用 origin 契约归一化工具）→ 构建（服务端按架构选 runner；electron 上 windows-2022；android 上 ubuntu-24.04）→ 发布（仅授权时）。
- 权限、证据上传、失败保留诊断的做法与既有 workflow 对齐。

## 新技能目录

```
skills/single-build-deploy/
  SKILL.md                 # 中文，结构对齐 full-build-deploy：范围/授权终点/阶段/必须停止情形
  tools/patch_release.py   # patch 编号推导、patch 记录生成与校验、发布编排
  tests/                   # 公式、编号推导、记录校验、workflow 结构测试
```

## 必须停止并报告的情形（技能文档需包含）

- base_revision 超过 current_revision，或基础批次发布证据缺失。
- patch 编号推导发现并发/撞号，或目标 tag/Release 已存在。
- hotfix commit 未固定到 sources.json 的受审提交，material_commit 不一致。
- origin 契约/TLS 模式/架构与批准输入不符。
- 任何需要覆盖、删除、替换既有产物的迹象。

## 留给实施者

- `patch_release.py` 的函数切分、CLI 形态、错误文案。
- 测试命名与夹具布局。
- 校验 `allocate-workflow.py`/`repository_counter.py` 是否在任何路径用 `derive()` 重算历史记录（当前阅读结论：只算新记录；实现时复核并留测试）。
- jitsi-mgr patch 发布资产的具体打包形态（沿用 build 产出的 artifacts 目录 + 证据即可）。

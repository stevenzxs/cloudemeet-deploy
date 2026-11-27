# Single Build Deploy（单服务/单客户端 patch 构建发布）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `skills/single-build-deploy` 技能与 `build-single.yml` 工作流：以已发布 joint 批次为基础，只构建并发布一个变更目标（八服务之一 / electron / android），版本不升 rN、以 `-patch.N` 区分，新建独立 Release，不触碰任何既有产物。

**Architecture:** ×10 预留 patch 位的统一版本公式（joint 与 patch 共用，仅新记录生效）；patch 记录为平行 schema，由新工具 `patch_release.py` 生成/校验；构建复用 `package.sh build` 与 `build-clients.cjs`；发布复用 `publish.py` 的 `require_absent`/`push_exact` 原语。

**Tech Stack:** Python 3（服务端工具）、Node 22 CJS（客户端工具）、GitHub Actions reusable/dispatch workflows、bash。

**Spec:** `docs/superpowers/specs/2026-11-27-single-build-deploy-design.md`

## Global Constraints

- 仓库治理：所有修改在修改分支上完成，测试通过后合入 main 并删除分支；不启动真实 Actions 构建/发布、不占号、不连接目标服务器。
- 版本公式（新记录统一）：`android_code = android_base_code×1000 + revision×10 + patch`（joint 时 patch=0）；`msi_version = major.minor.((client_patch+revision)×10 + patch)`；`pe_version = msi_version + '.0'`；patch ∈ 1..9。
- 数值示例（policy 基线 server=11248.0.1、client=1.0.21、android_base_code=1021）：r46 joint → `1021460` / `1.0.670` / `1.0.670.0`；r45-patch.1 → `1021451` / `1.0.661` / `1.0.661.0`。
- 已发布旧值（android_code ≤102145、MSI ≤1.0.66）不可变；新公式最小 joint 值 1021010 / 1.0.660 已大于全部旧值。
- patch 编号 N 由 `gh` 只读推导（匹配 `cloudmeet-<server_baseline>-r<base>-patch.*` 的 Release/tag 取 max+1），禁止手填；推送/建 Release 前二次检查，已存在即停。
- patch 记录 `kind: "patch"`、`version_formula: 2`、`request.target` 为具体目标；joint 校验器不扩展、不读 patch 记录。
- origin 契约/TLS/架构校验与 joint 一致；构建/发布阶段不访问目标 origin。
- 终点仅构建+发布；Release 证据必须标 `NOT_DEPLOYED`；`--latest=false`；先 draft 核验再公开。

## Review Focus

- **旧记录被新公式重算**：`validate_record` 只对本 Run 新记录调 `derive()`；任务 1 测试钉死"旧公式数值的记录不再通过新 derive"是有意行为，并复核 `allocate`/`revision_ledger`/`revision_git_ledger` 无任何路径重算历史记录。
- **patch 编号并发撞号**：两个同 base 的 patch Run 同时推导 N；workflow 设 `concurrency: cloudmeet-single-patch-<base_revision>`（cancel-in-progress: false），且发布前 `require_absent`/Release 存在性二次检查。任务 4/5 各有测试。
- **客户端 checkout 与 patch 记录漂移**：workflow 动态检出 sources.json 的 commit 后必须断言三方一致（checkout HEAD == sources.json == patch 记录 request.sources[target]）。任务 5 有结构测试。
- **MSI/PE 边界**：`(client_patch+revision)*10+9 > 65535` 时必须拒绝（revision 接近上限）。任务 1/2 测试覆盖。
- **jitsi-mgr 非镜像形态**：patch 发布资产是 JAR+前端目录而非镜像 tar.gz；发布路径不得假设存在镜像。任务 4 测试覆盖。

---

### Task 1: `revision_versions.py` 新公式 + Python 测试更新

**Files:**
- Modify: `skills/full-build-deploy/tools/revision_versions.py`（`derive()`）
- Test: `skills/full-build-deploy/tests/test_revision_versions.py`，并全量更新 `skills/full-build-deploy/tests/` 中钉死旧公式数值的用例（`test_revision_workflows.py`、`test_repository_counter.py`、`test_revision_git_ledger.py`、`test_revision_ledger.py` 等，以实际失败为准）

**Interfaces:**
- Consumes: 现有 `version-policy.json`（`server_baseline`/`client_baseline`/`android_base_code`/`namespace`）。
- Produces: `derive(policy, revision) -> dict`，返回键在现有基础上多 `version_formula: 2`；`android_code = base*1000 + revision*10`；`msi_version = f'{major}.{minor}.{(patch+revision)*10}'`。`validate_record` 签名不变。

- [ ] **Step 0: 合并已批准的设计文档分支**

```bash
git checkout main && git merge --ff-only docs/single-build-deploy-design && git branch -d docs/single-build-deploy-design && git push origin main
```

- [ ] **Step 1: 新建修改分支**

```bash
git checkout -b feat/single-build-deploy
```

后续所有任务都在此分支上逐个提交，全部完成后合回 main。

- [ ] **Step 2: 写失败测试**（更新 `test_revision_versions.py` 的核心用例）

```python
def test_derive_reserves_patch_band(self):
    v = derive(self.policy, 46)
    self.assertEqual(v['android_code'], 1021460)
    self.assertEqual(v['msi_version'], '1.0.670')
    self.assertEqual(v['pe_version'], '1.0.670.0')
    self.assertEqual(v['client_version'], '1.0.21+r46')
    self.assertEqual(v['version_formula'], 2)

def test_derive_rejects_msi_range_exhaustion(self):
    with self.assertRaises(ValueError):
        derive(self.policy, 6554)  # (21+6554)*10+9 = 65759 > 65535
```

（按现有测试文件的 policy 夹具调整 self.policy 构造。）

- [ ] **Step 3: 运行确认失败**

Run: `python -B -m unittest discover -s skills/full-build-deploy/tests -p test_revision_versions.py`
Expected: FAIL（新断言对旧公式不成立）

- [ ] **Step 4: 修改 `derive()`**

`code = base * 1000 + revision * 10`；`msi` 第三段改为 `(patch + revision) * 10`；范围校验改为 `(patch + revision) * 10 + 9 > 65535` 时拒绝；返回值追加 `version_formula=2`。`previous_android_code`/`previous_msi_version` 下限校验逻辑不变。

- [ ] **Step 5: 全量跑 skills Python 测试，逐一更新钉死旧数值的夹具**

Run: `python -B -m unittest discover -s skills/full-build-deploy/tests -q`
Expected: PASS（允许与 main 基线一致的 2 个既有失败/26 个 Windows 环境错误之外无新增失败；凡是公式数值导致的失败都改夹具，新旧值对应关系：`int(str(base)+str(r))` → `base*1000+r*10`，`patch+r` → `(patch+r)*10`）

- [ ] **Step 6: 复核无历史记录重算路径**

Run: `grep -rn "derive(" skills/full-build-deploy/tools/`
Expected: `derive` 调用点仅用于"新分配 revision"（`repository_counter.allocate`、`revision_ledger`、`revision_git_ledger` 的 `len+1` 调用）和 `validate_record` 对本 Run 记录的重算；无历史记录重算。

- [ ] **Step 7: Commit**

```bash
git add skills/full-build-deploy/tools/revision_versions.py skills/full-build-deploy/tests/
git commit -m "feat(full-build-deploy): reserve patch band in client version formula"
```

### Task 2: `core.cjs` versionCode/parseConfig 新公式与 patch 后缀

**Files:**
- Modify: `skills/full-build-deploy/tools/clients/core.cjs`（`versionCode()`、`parseConfig()` assignment 校验分支）
- Test: `skills/full-build-deploy/tools/clients/tests/core.test.cjs`、`revision.test.cjs`、`cli.test.cjs`（夹具数值）、`shortcuts.test.cjs`（如引用派生数值）

**Interfaces:**
- Consumes: Task 1 的公式（两侧必须一致）。
- Produces:
  - `versionCode(version: string) -> number`：支持 `1.0.21`（1021，不变）、`1.0.21+r45`（1021450）、`1.0.21+r45-patch.1`（1021451）；patch 段只接受 1..9 单个数字。
  - `parseConfig(text, assignment)`：assignment 的 `versions` 含整数 `patch`(1..9) 时按 patch 分支校验：`client_version === '<base>+r<revision>-patch.<patch>'`、`msi_version` 第三段为 `(parts[2]+revision)*10+patch`；否则走 joint 分支（第三段 `(parts[2]+revision)*10`）。

- [ ] **Step 1: 写失败测试**（`core.test.cjs`）

```js
test('Android code reserves patch band per revision', () => {
  const { versionCode } = require('../core.cjs');
  assert.equal(versionCode('1.0.21'), 1021);
  assert.equal(versionCode('1.0.21+r45'), 1021450);
  assert.equal(versionCode('1.0.21+r45-patch.1'), 1021451);
  assert.equal(versionCode('1.0.21+r45-patch.9'), 1021459);
  for (const s of ['1.0.21+r45-patch.0', '1.0.21+r45-patch.10', '1.0.21+r0', '1.0.21+r01'])
    assert.throws(() => versionCode(s));
});
```

`revision.test.cjs` 增加 patch assignment 的 parseConfig 正反用例（`versions: { revision: 45, patch: 1, client_version: '1.0.21+r45-patch.1', android_code: 1021451, msi_version: '1.0.661', pe_version: '1.0.661.0' }` 通过；`android_code: 102145` 抛错）。

- [ ] **Step 2: 运行确认失败**

Run: `node --test "skills/full-build-deploy/tools/clients/tests/*.test.cjs"`
Expected: 新用例 FAIL

- [ ] **Step 3: 实现**

`versionCode` 改为：先匹配 `^(.*)\+r([1-9]\d*)-patch\.([1-9])$`（返回 `versionCode(base)*1000 + r*10 + p`），再匹配 `^(.*)\+r([1-9]\d*)$`（返回 `versionCode(base)*1000 + r*10`），基础形式不变；保留 safeInteger 与 ≤2100000000 检查。`parseConfig` assignment 校验按 Interfaces 的双分支重写，范围检查改 `(parts[2]+revision)*10+9 > 65535` 拒绝。

- [ ] **Step 4: 全量客户端测试，更新旧数值夹具**

Run: `node --test "skills/full-build-deploy/tools/clients/tests/*.test.cjs"`
Expected: PASS（`cli.test.cjs` 的 `10211`/`1.0.22` 等夹具按新公式换算：`1.0.21+r1` → code 1021010、msi 1.0.220）

- [ ] **Step 5: Commit**

```bash
git add skills/full-build-deploy/tools/clients/core.cjs skills/full-build-deploy/tools/clients/tests/
git commit -m "feat(clients): patch-aware version code and assignment validation"
```

### Task 3: `package.sh` VERSION 正则 + `revision-config.cjs` patch 记录

**Files:**
- Modify: `skills/full-build-deploy/scripts/package.sh:14`
- Modify: `skills/full-build-deploy/tools/clients/revision-config.cjs`（`loadAssignment`）
- Test: `skills/full-build-deploy/tests/test_workflow_isolation.py`（如对 VERSION 正则有断言则同步）；`skills/full-build-deploy/tools/clients/tests/cli.test.cjs` 增加 patch 记录接受用例

**Interfaces:**
- Consumes: Task 2 的 parseConfig patch 分支。
- Produces:
  - `package.sh` 接受 `VERSION=11248.0.1+r45-patch.1`（正则 `^[0-9]+(\.[0-9]+){2,3}\+r[1-9][0-9]*(-patch\.[1-9])?$`）。
  - `loadAssignment(file, root, target, env)`：记录含 `kind === 'patch'` 时额外要求 `record.request.target === target` 且 `record.versions.patch` 为 1..9 整数；既有 `configuration_sha`/`run_id`/scope 绑定校验不变。

- [ ] **Step 1: 失败测试**（`cli.test.cjs`：构造 `kind:'patch'`、`request.target:'electron'`、`request.scope:['electron']` 的 patch 记录，跑 `--target electron --check` 路径，断言不因记录形态抛错；再把 target 改成 `android` 断言抛错）

- [ ] **Step 2: 运行确认失败** — Run 同 Task 2 Step 2。

- [ ] **Step 3: 实现两处修改**（`package.sh` 一行正则；`loadAssignment` 增加 patch 分支）

- [ ] **Step 4: 验证**

Run: `node --test "skills/full-build-deploy/tools/clients/tests/*.test.cjs"` 与 `bash -n skills/full-build-deploy/scripts/package.sh` 与 `python -B -m unittest discover -s skills/full-build-deploy/tests -p test_workflow_isolation.py`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/full-build-deploy/scripts/package.sh skills/full-build-deploy/tools/clients/revision-config.cjs skills/full-build-deploy/tools/clients/tests/ skills/full-build-deploy/tests/
git commit -m "feat(full-build-deploy): accept patch version identity in build entry points"
```

### Task 4: 新技能工具 `patch_release.py` + 测试

**Files:**
- Create: `skills/single-build-deploy/tools/patch_release.py`
- Create: `skills/single-build-deploy/tests/test_patch_release.py`

**Interfaces:**
- Consumes: `skills/full-build-deploy/tools/revision_versions.py` 的 `digest`/`numeric_version`（sys.path 引入，沿用 joint-release.py 的 importlib/sys.path 模式）；`skills/full-build-deploy/tools/publish.py` 的 `require_absent(remote)`、`push_exact(remote)`、`digest(path)`、`matches_config`；`version-policy.json`；`sources.json`。
- Produces（CLI，均 `python3 -B` 调用）：
  - `patch_release.py allocate --base-revision N --target T --output FILE`：只读推导 patch 号并写出 patch 记录 JSON。记录结构：`{ namespace, kind: 'patch', request: { repository, workflow, run_id, configuration_sha, sources(=当前 sources.json 全量+生命周期+h5, 同 allocate-workflow.py 的 identities), target, base_revision, patch, task, scope: [粗粒度] }, versions: { revision, patch, version_formula: 2, server_version, server_tag, client_version, android_code, msi_version, pe_version }, allocation_sha256 }`。scope 映射：八服务→`['server']`，electron/android→同名。
  - `patch_release.py check-base --base-revision N --target T`：基础批次发布证据核验（非 draft Release 前缀匹配 `cloudmeet-<server_baseline>-r<N>-*`；服务端目标另查 GHCR `cloudmeet-<service>:<server_baseline>-r<N>` tag 可解析 digest；客户端目标另查 Release 资产含对应扩展名）。缺一即非零退出。
  - `patch_release.py publish --target T --input DIR`：发布编排（服务端：GHCR 推送 `ghcr.io/stevenzxs/cloudmeet-<service>:<server_tag>-patch.<N>`，复用 `require_absent`/`push_exact`，记录 digest；随后建 Release `cloudmeet-<server_tag>-patch.<N>`，draft→核验→公开、`--latest=false`；资产=镜像 tar.gz+证据+SHA256SUMS，jitsi-mgr 为 artifacts tar.gz+证据）。客户端发布只建 Release（MSI/APK+证据+SHA256SUMS），不推 GHCR。
- `next_patch(existing_tags: list[str], prefix: str) -> int`：纯函数，从 tag 列表解析 `prefix + '.patch.'`？不——tag 形如 `cloudmeet-11248.0.1-r45-patch.3`，prefix 为 `cloudmeet-11248.0.1-r45-patch.`，取 max+1，无任何匹配返回 1；解析到非预期格式跳过。

- [ ] **Step 1: 失败测试**

覆盖：`next_patch`（空列表→1；`['...-patch.1','...-patch.3']`→4；混入 `patch.10` 之外的脏 tag 不误解析；同 base 已到 9 再推导→抛错"patch 位耗尽"）；`build_record`（给定 policy/sources/run 上下文产出记录，`allocation_sha256` 自校验往返一致；`base_revision > current_revision` 抛错；target 非法抛错）；版本字段与 Task 1/2 公式一致（r45-patch.1 → 1021451/1.0.661/1.0.661.0）；`check-base` 的 Release/tag 解析逻辑（mock 子进程/gh 输出：draft 被排除、前缀误匹配 `r4` 不匹配 `r45`、缺客户端资产报错）；jitsi-mgr 发布资产形态不含镜像 tar.gz 的断言。

- [ ] **Step 2: 运行确认失败**

Run: `python -B -m unittest discover -s skills/single-build-deploy/tests -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `patch_release.py`**

`gh` 调用统一封装为可注入的 runner 函数（默认 `subprocess.run`），测试注入假输出。GHCR tag 存在性/digest 解析复用 `publish.py` 原语与 `docker buildx imagetools inspect`（runner 上凭 GH_TOKEN 认证，与 publish.py 现状一致）。

- [ ] **Step 4: 运行确认通过** — Run 同 Step 2。Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/single-build-deploy/
git commit -m "feat(single-build-deploy): patch release record, numbering and publish tool"
```

### Task 5: `build-single.yml` 工作流 + 结构测试

**Files:**
- Create: `.github/workflows/build-single.yml`
- Test: `skills/single-build-deploy/tests/test_workflow_structure.py`

**Interfaces:**
- Consumes: Task 4 的 CLI；`origin_contract.py`/`tls_contract.py`（origin 归一化，用法照 `revision-allocation.yml`）；`package.sh build`（Task 3）；`build-clients.cjs`（Task 2/3）。
- Produces: dispatch inputs：`base_revision`(string, required)、`target`(choice: gateway/app-web/api/jitsi-mgr/web/prosody/jicofo/jvb/electron/android, required)、`expected_tls_mode`(choice)、`expected_origin`(string)、`material_commit`(string)、`architecture`(choice amd64/arm64，仅服务端目标使用)、`publish_images`(boolean, default false)。jobs：`version`（origin 契约 + `patch_release.py allocate` + `check-base`，输出 `assignment`/`origin_contract`）→ `build`（按 target 分流：服务端在架构对应原生 runner 跑 `package.sh build <target>`，env `VERSION`/`BATCH`/`VERSION_RECORD` 取自 patch 记录——`BATCH=<server_tag>-patch.<N>-<run_id>-<attempt>`；electron 在 windows-2022、android 在 ubuntu-24.04，流程照 `build-clients.yml` 的 material 校验/批次 env 生成/依赖安装/构建步骤，客户端源码 checkout 的 `ref` 从 `sources.json` 对应条目读出并断言三方一致）→ `publish`（`if: inputs.publish_images`，下载构建 artifact，跑 `patch_release.py publish`）。`concurrency: group: cloudmeet-single-patch-${{ inputs.base_revision }}-${{ inputs.target }}`, `cancel-in-progress: false`。

- [ ] **Step 1: 失败结构测试**（断言：workflow 可解析为 YAML；含全部必需 inputs；`concurrency` 组存在且不取消在途；客户端 job 含"sources.json 读 ref + 三方一致断言"步骤且不含硬编码 40 位 commit；publish job 受 `publish_images` 门禁；不出现 `build-tools/`；服务端 job 设置 `VERSION_RECORD` 指向 patch 记录文件）

- [ ] **Step 2: 运行确认失败**（文件不存在）

- [ ] **Step 3: 实现 `build-single.yml`**（结构参照 `build-clients.yml` 与 `build-package.yml`；action 版本沿用既有 pin 的 SHA）

- [ ] **Step 4: 验证**

Run: `python -B -m unittest discover -s skills/single-build-deploy/tests -q` 与 `python -B -m unittest discover -s skills/full-build-deploy/tests -p test_workflow_isolation.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/build-single.yml skills/single-build-deploy/tests/
git commit -m "feat(single-build-deploy): single-target patch build/publish workflow"
```

### Task 6: 技能文档与受影响文档同步

**Files:**
- Create: `skills/single-build-deploy/SKILL.md`
- Modify: `skills/full-build-deploy/SKILL.md`（版本规则一句：新公式与 patch 后缀，指向设计文档）
- Modify: `skills/full-build-deploy/tools/clients/README.md`（"Android versionCode自动转换"一节更新为新公式 + patch 规则）
- Modify: `AGENTS.md`（如技能清单登记了 full-build-deploy，则补 single-build-deploy 一行；先读确认格式）

**Interfaces:**
- Consumes: 设计文档全文。
- Produces: `SKILL.md` 结构对齐 full-build-deploy（交付范围与产物/任务终点与授权/阶段/必须停止并报告的情形），明确：仅构建+发布、不部署；patch 编号只读推导；不替换既有产物；停止情形清单照设计文档"必须停止并报告的情形"。

- [ ] **Step 1: 写 SKILL.md 与两处文档修改**

- [ ] **Step 2: 一致性检查**

Run: `grep -rn "build-tools/" skills/ .github/ AGENTS.md README.md`
Expected: 无输出（发现即修）

- [ ] **Step 3: Commit**

```bash
git add skills/single-build-deploy/SKILL.md skills/full-build-deploy/SKILL.md skills/full-build-deploy/tools/clients/README.md AGENTS.md
git commit -m "docs: single-build-deploy skill and version formula docs"
```

### Task 7: 全量验证与分支闭环

- [ ] **Step 1: 全量测试**

Run: `python -B -m unittest discover -s skills/full-build-deploy/tests -q`；`python -B -m unittest discover -s skills/single-build-deploy/tests -q`；`node --test "skills/full-build-deploy/tools/clients/tests/*.test.cjs"`；`python -B tools/check-deployment-layout.py`；`bash -n skills/full-build-deploy/scripts/package.sh`
Expected: 除 main 基线既有失败/环境错误（2 failures/26 errors/根 tests 5 errors）外全部 PASS，无新增失败

- [ ] **Step 2: `git diff --check` 与最终 diff 自查**（无秘密、无 patch 编号手填、无 build-tools 引用）

- [ ] **Step 3: 合回 main 并删除分支、推送**

```bash
git checkout main && git merge --ff-only feat/single-build-deploy && git branch -d feat/single-build-deploy && git push origin main
```

- [ ] **Step 4: 报告**

列出：各任务 commit、公式变更前后数值对照、未执行项（真实 Actions 运行/发布/部署均未执行，等待用户显式发起 `build-single.yml`）。

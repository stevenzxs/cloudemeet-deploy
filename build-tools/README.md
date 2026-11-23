# CloudMeet Actions compilation and packaging

唯一维护源为部署仓库中的本目录；部署规范见 `../AGENTS.md`。工作区不需Docker。Actions从同一提交检出工作流、build-tools、config及patches，不再人工同步CI分支副本。

## 唯一正常入口

CloudMeet标准联合交付/短提示词操作入口见 `../skills/cloudmeet-online-delivery/SKILL.md`。
唯一用户参数是完整origin及任务终点，`delivery-target.py --origin <origin>`只读派生统一网络值；
`--target-env <仓库外路径>`另存实例配置，不改不可变包。联合工作流为build-joint.yml，
Windows明确unsigned，Android保持原批准身份签名；两端HTTPS限定信任不变。规则安装/辅助回归不是端到端交付通过。

## 线上发布与离线附加节点（2026-11-23）

- 联合入口`build-joint.yml`先完成七服务和两客户端；`publish_images=true`只在本次发布已授权时启用，调用`publish-release.yml`核对同Run/attempt、分配记录、配置/源码身份、origin及公开CA。七镜像发布GHCR；MSI/APK、无镜像线上材料、setup.py、registry及摘要持久发布同一GitHub Release。draft资产全部上传后才公开，失败保留部分状态，不覆盖同批标签。
- `delivery-route.py --origin <已构建入口>`只提示缺少的first/upgrade和server，不SSH。已有选择用`--mode`/`--server`传入；升级须补实际`--root`/`--project`/`--target-env`。入口/CA构建前确定，发布后不得静默改变。
- 线上首装：先可信核验Release的SHA256SUMS，独立安全提供相邻cert.tar.gz，使用`python3 -B setup.py --server-package <online.tar.gz> --verify-origin <origin> --target-env <包外绝对路径> --registry <registry.json> --registry-sha256 <可信摘要>`。setup拒绝已有解压目录，安装核心按digest拉取。需要已有匹配Linux Docker Engine，包内Compose不等于Docker首装能力。
- 线上升级：从已核验新材料运行`python3 -B <新材料>/online_update.py --root <实际实例> --project <实际project> --target-env <包外绝对路径> --verify-origin <origin> --ca <公开根> --candidate <新材料>/candidate.json --registry <registry.json> --registry-sha256 <可信摘要>`，默认只读；本次升级已授权时加`--apply`。仅image-only，外置补丁或配置变化须另行迁移适配，不能清数据重装绕过。
- 离线导出：在已批准且Docker可用的匹配Linux构建/导出机，以干净固定配置SHA执行`python3 -B build-tools/offline-export.py --source <已核验解压线上材料> --registry <registry.json> --registry-sha256 <可信摘要> --destination <全新批次目录>`。从registry固定digest拉取/核验后save，不编译/新占rN；保留原镜像构建配置SHA，另记导出配置SHA。输出离线归档/摘要和setup.py/摘要，目标不联网补包。
- 离线首装同setup命令但不传registry；离线升级同升级命令并加`--offline-package <新材料目录>`，registry使用包内文件的独立可信摘要，只load不pull。保留秘密/数据/CA，七容器归属、空闲、SQLite一致性备份和旧image ID恢复均不省略。
- 本次仅辅助脚本回归；未触发真实Actions、GHCR/Release发布、Docker、目标安装/升级或媒体。历史r14不恢复、不追改，真实验收另行授权。

本节是服务端Actions入口；Windows MSI/Android APK的独立本机构建入口为
`clients/build-clients.cjs`，配置唯一读取`deploy/config/client.env`，先运行
`node build-tools/clients/build-clients.cjs --target all --check`。
版本状态证据、工具链及候选验证边界见[客户端工具说明](clients/README.md)。

将本目录受控同步至部署仓库的 `build-tools/`，将 `build-package.yml` 同步至
`.github/workflows/build-package.yml`；公开补丁仍来自部署仓库 `patches/`。
审核并提交推送这些文件后，在 GitHub Actions 选择 **CloudMeet compile and package aarch64**：

- 版本不再手填：共同修订号由受控持久台账分配，具体映射和启用门槛见下文。
- `material_commit`：包含本次脚本、补丁及配置的完整40位提交SHA，必须等于所选workflow提交。
- 地址与端口：`config/target.env`不绑定网页入口IP，仅设置协议、端口及可选媒体IPv4覆盖。Caddy使用本地证书和通配路由，接受证书告警/客户端兼容性限制；信令由启动器生成的custom-config.js跟随浏览器入口。`config/jitsi.env`保留公共参数。

工作流只读仓库，不需要SSH或registry秘密，不自动发布镜像。每次run/attempt完整编译七服务；
入口仅受控手动触发；移除push触发和默认版本回退。默认不发布，显式批准publish_images时仅发布job取得GHCR写权限。
失败则无最终包，不跨run/attempt补旧镜像。**重跑请选择全部jobs**，不能仅重跑失败job后混用旧attempt。
Docker build中的依赖和构建层缓存允许复用，但输出应用镜像必须由本批build步骤产生。

`package.sh build SERVICE`构建一个锁定源码服务，输出`output/SERVICE/{SERVICE.tar.gz,SERVICE.json}`。
`package.sh assemble`仅接收本run/attempt的`incoming/SERVICE/`，执行材料检查、生成最终包。
这两个命令由工作流设置VERSION、BATCH和GitHub运行身份；不在Windows/WSL运行服务器构建或组包。

## 输出及安装边界

### 联合版本入口（2026-11-19）

`.github/workflows/build-joint.yml`一次分配后调用七服务及双客户端工作流；
独立服务端/客户端入口使用相同命名空间，子工作流只核验已有父Run记录。
`revision_versions.py`派生显示与平台字段，`revision_git_ledger.py`在专用
cloudmeet-revision-ledger分支用非强推Git CAS持久化；已分配失败不回收，同Run attempt复用并追加attempt证据。
包内来源记录和provenance/version-assignment.json绑定完整分配身份。

目前**配置已批准启用、控制端未就绪**：config/version-policy.json的approved=true，
服务端基线11248.0.1；用户批准以现存正式包Android1021/MSI1.0.21为兼容基线，
不明更早测试包不在覆盖升级保证内，核验摘要见VERSION-ACTIVATION.md。客户端映射为
1.0.21+rN、Android int('1021'+N)、MSI 1.0.(21+N)、PE 1.0.(21+N).0。
当前批准方案为GitHub-hosted ubuntu-24.04分配，不恢复旧Runner id21或安装新150 Runner。
现存SQLite r1–r14须完整只读迁移，迁移计划与边界见controller/README.md；本次未发布ledger分支、
未设置CLOUDMEET_LEDGER_ANCHOR、未迁移或分配正式编号。缺锚/分支拒绝自动初始化。
独立备份保留最近7天，不取消备份；启用前验证备份恢复及独立Run高水位，不能只信有效旧快照。
GitHub仓库写权限、分支防改写和实际Actions验收仍须分别核验。

首次实际交付前仍需核验Windows签名身份/适用签名要求、真实MSI/PE/APK映射和覆盖升级；
代码辅助回归不代表签名/云端/客户端/媒体通过。服务原生版本仍见sources.json，
联合交付版本不能覆盖上游身份。预检、查询、下载和部署既有制品不分配N。

最终artifact `cloudmeet-aarch64-RUN-ATTEMPT` 包含：

- `cloudmeet-BATCH-aarch64.tar.gz`及独立`.sha256`；
- `package-evidence.json`，只报告材料检查，不是安装或会议验收。

包内有七镜像、源码/镜像来源、Compose、配置、公开补丁、INSTALL、SHA256SUMS及公共安装核心。
目标需预先具备匹配Linux/aarch64 Docker Engine与Python≥3.7；本包不含Docker或宿主OS。
安装仅由用户按包内INSTALL显式运行；不联网补依赖、不build/pull、不覆盖既有env/data。
安装/客户端/媒体后续单独验收，镜像发布必须使用本包原镜像而非重建。

下载后在`deploy/release/aarch64/server/BATCH/`保留原artifact包，先核对外层归档SHA256，
再核对解包的SHA256SUMS；给出实际路径与来源后才称交付完成。下载不在此编译脚本中隐式执行。

## 维护验证（均无Docker）

```text
wsl -d Ubuntu-24.04 -- bash -n /mnt/d/code/jitsi/build-tools/package.sh
wsl -d Ubuntu-24.04 -- python3 -B -m unittest discover -s /mnt/d/code/jitsi/build-tools/tests -p test_*.py
python -B deploy/tools/check-deployment-layout.py
```

修改受控输入后重新生成`inputs.sha256`并核对CI副本；禁止手工跳过校验。
新工作流不调用旧诊断工作流。`build-tools-old/`和历史包保留，不作为本入口的运行依赖。
## 主持人转让默认集成（2026-11-12）

按用户确认及 `../AGENTS.md`，所有新正常部署默认开启主持人转让。`package.sh` 外置交付公开插件及引用，`offline-runtime/initialize.py` 目标生成API共享鉴权秘密和内部TLS材料，`offline-runtime/start.py` 安装插件并生成模块/接口配置。网关内部HTTPS不发布宿主端口，公网拒绝内部接口，Prosody严格验证CA。私钥及实例秘密不进镜像或包；不能以首次初始化覆盖已有实例。

找回及管理员恢复仍默认关闭，必需材料或配置缺项报错，不静默降级。包级校验与部署后轮换/撤权/接收确认/恢复验收分开。当前代码仍在收尾，CI受控副本/摘要及完整回归待核对；不表示已构建或已启用。继续使用Actions原生aarch64七服务主流程，不新增补丁交付线。
# Native architecture selection (2026-11-13)

## Target-side private certificate input

Actions outputs setup.py and setup.py.sha256 alongside the server archive and its checksum.
Do not upload cert.tar.gz to Git/Actions. Copy it securely beside those files on target.
After checking both SHA256 sidecars, run:
`sudo python3 -B setup.py --server-package <server.tar.gz> --verify-origin https://<host>:<port> --target-env /absolute/path/instance-target.env`.
Copy the packaged target.env outside the extracted package and set explicit MEDIA_HOST
and ports there. Do not modify package bytes or checksums. deploy validates parameters
and rendered Compose before image imports or secret initialization. Only public target
values are inherited by initialize/start; reports are retained beside the package in
`<package-name>-network-preflight/`. Keep that external instance file stable for the
installation; direct start recovery must explicitly set CLOUDMEET_TARGET_ENV to the
same absolute path. There is no automatic first-install retry or data deletion.
Preflight/start now share a controlled environment resolver: jitsi.env, validated
instance values and exact generated secrets, not arbitrary parent interpolation.
The effective target fingerprint is pinned for child phases; changed values abort.
This installer is direct-entry: verify-origin port must equal HTTPS_PORT and public
gateway/JVB bindings must be wildcard. External proxy/port translation needs an
explicitly reviewed contract rather than bypassing these checks.
setup refuses an existing installation directory. It stages cert.tar.gz and cert/ without
changing the original package SHA256SUMS; the verifier permits only exact certificate
members matching the checked archive. Certificate SAN, expiry, chain and key are checked
before image imports. After startup only gateway is restarted; strict TLS/2xx verification
uses ca.crt and the explicit origin. Failures preserve secrets/data for manual recovery.
No automatic retry of first-install, target cleanup or server operations during packaging.

The single workflow accepts `architecture: amd64|arm64` (default arm64).
amd64 uses native ubuntu-24.04; arm64 uses native ubuntu-24.04-arm.
`TARGET_ARCH` controls the runner check, image platform, Java/Go toolchain,
bundled Compose, archive identity and Linux existing-engine target profile.
No emulation, local Docker, registry publication or target installation is part of packaging.
The Jitsi stable-11248 base is pinned to its multiarch index; its ARM child remains unchanged.
# Network audit (2026-11-19)

`package.sh build/assemble` runs `network-audit.py` before build work. Assembly
checks normalized Compose without starting containers, and retains JSON/Markdown
under `output/network-audit-*/` and package `provenance/network-*`. Failed jobs
upload separate audit artifacts. New packages require a target-mode audit at
first startup. Generic empty MEDIA_HOST is **deferred**, not media-ready; provide
a usable client-reachable IPv4 before starting. Private LAN IPs are valid inputs.

Read-only manual example (no Docker):
`python -B build-tools/network-audit.py --root . --mode generic --output <new-audit-directory>`

Reports inventory template declarations and fixed endpoints with source lines,
input hashes, source/config SHA and run identity. Rendered environments log only
network keys, not credentials. Target routes, NAT, UDP, actual ICE, TLS and media
remain unverified. Keyword discovery is not proof that every dynamic source path
is covered; new consumption paths require reviewed inventory/test updates.

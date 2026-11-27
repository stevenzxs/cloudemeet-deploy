---
name: cloudmeet-full-build-deploy
description: Use when the user explicitly requests a complete CloudMeet GitHub delivery from source through deployment and acceptance, covering all eight services and both clients. Also use to prepare or execute only the explicitly requested build, publication, or deployment stages without crossing the requested endpoint.
---

# CloudMeet GitHub 全量构建、发布、部署与验收

本技能覆盖 CloudMeet 八个服务和两个客户端的联合交付。它是操作步骤，不构成额外的授权；不得因“全量”“完整”或本技能被调用而推定用户已授权发布、部署、数据迁移、证书切换或破坏性操作。只执行用户明确要求的终点。不得读取或依赖另一份操作文档来补齐本技能；本文没有写明且无法从受控工作流/脚本接口确认的事项，停止并报告，不猜测。

## 交付范围与产物

八个服务：`web`、`app-web`、`api`、`jitsi-mgr`、`gateway`、`prosody`、`jicofo`、`jvb`。七个服务构建容器镜像；`jitsi-mgr` 构建后端 JAR 和静态管理前端，由网关托管。两个客户端：Electron Windows MSI（明确 unsigned）和 Android APK（只使用仓库已批准的签名身份/密钥）。服务端还包含 H5 资产。不得把客户端签名身份、上游版本或受信任 HTTPS CA 在本任务中自行更换。

联合交付使用 GitHub Actions `build-joint.yml`，在同一父 Run/attempt 与分配记录中生成服务端、H5、Electron、Android 证据。可发布时，GHCR 镜像、MSI/APK 和线上安装材料必须由同一经核验批次发布；服务端/客户端构建与发布均不等于已部署或已完成真实端到端验收。

## 任务终点与授权

- “检查、预检、计划、仅构建”只进行只读核验或构建，不发布、不连接服务器、不安装。
- “构建并发布”可运行构建及本批发布；发布不包含目标服务器操作。
- “构建、发布并部署/完整交付”只有在请求清楚覆盖目标、首次安装或升级方式、并明确授权相应目标变更时，才继续部署。若服务器身份、目标路径、首次安装/升级状态或必要授权不明，停止在安全阶段并一次性报告缺项，不猜测、不将升级改成首装。
- 已明确请求一条完整链时，不对已批准固定选项逐步重复询问；但不得把缺失的目标身份或授权当作固定选项。删除、覆盖、模式迁移等破坏性/特殊动作必须有清楚具体的授权。
- 维护本技能文件不是启动 Actions、正式分配版本、发布或连接目标的授权。

## 阶段一：同步与预检

1. 先检查配置仓库远端身份、分支、当前完整 SHA、工作区、工作树占用和在途任务；再安全同步已批准 `origin/main`，仅在无冲突、可快进且不会覆盖本地/并发工作时进行。遇到脏工作区、分叉、认证或网络失败，保留现场并报告，不 reset、不强制覆盖、不删工作树、不拿旧副本冒充最新状态。记录实际使用的完整配置提交 SHA。
2. 核对本次所需 GitHub 仓库权限、Actions 可用性、客户端签名材料可用性（不显示秘密）、目标平台和部署授权。GitHub 官方 API、Actions、push、GHCR 走官方认证接口；公开源码/只读下载可优先使用用户已批准的公开只读加速入口，但校验仍须独立可信，API、私有资源、令牌和镜像不得送往公开代理。TLS、摘要或身份不匹配时停止；不得用 `-k`、跳过摘要或直接执行未核验下载内容。
3. 从请求取得完整 HTTPS `origin`（协议、主机、端口）和任务终点。配置中的 TLS 模式只能是本次明确批准且与固定配置一致的 `private-ca` 或 `caddy-public-acme`；不得从仓库默认值猜本次批准，也不得为通过门禁改写批准值。TLS 模式、origin、客户端证据和服务端候选必须绑定同一批次。模式切换不是普通升级；无专用、已验证迁移路径时停止。
4. 确认配置修改已在所选提交中固定；`material_commit` 必须是该受审配置提交的完整 SHA，并与工作流提交要求相符。检查受控源码来源固定到完整提交、八服务和双客户端清单齐全、无秘密进入 Git/包/镜像。缺少固定身份或配置/来源不一致时，不启动占号构建。
5. 确认架构为用户批准的 `amd64` 或 `arm64`。构建之前显示将执行的阶段、origin、TLS 模式、架构、配置 SHA、是否发布及（如获授权）目标服务器标识；不得显示令牌、私钥、密码或签名秘密。

## 阶段二：联合构建与版本分配

1. 使用 `build-joint.yml` 的 `workflow_dispatch`，输入本次批准的 `expected_tls_mode`、`expected_origin`、完整 `material_commit`、`architecture`。该入口一次构建服务端与两个客户端；客户端目标固定为 `electron` 和 `android`。
2. 仅在用户明确授权本批发布时设置 `publish_images=true`；否则为 `false`。该参数会请求联合 GHCR 与 GitHub Release 发布，不是“仅构建”开关。它不授权部署。
3. 由仓库内版本配置为新的顶层 Run/attempt 分配共同 `rN`；分配来源是 `skills/full-build-deploy/config/version-policy.json` 中的 `current_revision`，不手填、猜测、回收或重建编号。已分配后失败或取消也消耗编号；同一 Run 的新 attempt 视为新的构建尝试并消耗新编号。修复材料后需新 Run/新编号。不得只重跑失败子 job 后与旧 attempt 混包；重跑必须重跑完整父工作流。客户端数字版本自 2026-11-27 起采用预留 patch 位公式：`android_code = android_base_code×1000 + rN×10`，MSI 第三段 `(client 基线 patch + rN)×10`；末位 1..9 预留给 single-build-deploy 的 patch 发布（见 `docs/superpowers/specs/2026-11-27-single-build-deploy-design.md`）。
4. 跟踪父 Run 及全部必需 job 到终态。核对同一 Run/attempt、版本分配记录、配置 SHA、固定源码 SHA、TLS 模式、origin、架构和服务端/双客户端证据。任何必需项失败、缺失或彼此不一致，停止，不发布、不拼接旧产物、不报告为完整构建。
5. 构建成功仅表示自动化产物/材料检查成功。保存 Run URL/ID、attempt、分配版本、artifact ID/名称、摘要及证据位置；不把它表述为发布、安装或会议媒体验收通过。

## 阶段三：联合发布

1. 仅当 `publish_images=true` 已由本次明确授权且所有本批必需构建 job 成功，才允许发布 job 执行。发布器必须核验同一父 Run/attempt、分配记录、源码/配置身份、架构、TLS/origin 及双客户端材料。
2. 发布内容为本批七个服务镜像到 GHCR，以及 MSI、APK 和线上部署材料到同一 GitHub Release。镜像以摘要/digest 固定引用；资产 checksum 必须来自独立可信发布材料。不得覆盖既有批次标签，不得将不同 Run/attempt 的文件混入 Release。
3. 核对 Release 的资产清单、SHA256SUMS、各文件摘要、镜像 digest、Release 状态和工作流结果。若发布部分失败，保留并报告部分状态，不谎称完整发布、不擅自覆盖或清理。Release 证据必须明确标示 `NOT_DEPLOYED`；发布不证明公网 ACME 签发/续期或目标证书状态。

## 阶段四：目标识别和部署前保护

仅在用户请求到达部署终点且授权明确时进行。首装与升级是互斥路径：先只读核对目标主机身份、CPU 架构、当前容器/项目、数据卷、目录、端口、Docker Engine、证书模式及运行状态；请求路径与真实状态不一致即停止。不得把“首装”解释为清理旧实例，也不得用重装绕过升级失败。

部署前必须：

- 使用已核验 Release 的确切资产和可信摘要，确认其共同批次、origin、TLS 模式、架构与部署请求一致；镜像拉取/导入必须固定到发布 digest，不重新构建、不使用浮动 tag。
- `private-ca`：保护原 CA 根与客户端信任；证书包经独立安全渠道提供并校验。私钥不得进仓库、Actions artifact、镜像或交付包。
- `caddy-public-acme`：需目标域名 A/AAAA、主机身份、443 直达、公共 CA 信任和出站 DNS/HTTPS 条件可核实；保留 Caddy `/data` 与 `/config` 持久卷。签发失败不得静默回退 private CA。部署前条件检查不等于实际签发或续期验收。
- 首装：只在确认目标没有既有实例、用户授权首装、实例配置保存于包外并有绝对路径时运行安装器；验证 Release 安装材料与 checksum。安装器拒绝既有解包目录时停止，不删除目录重试。目标须预先具备兼容架构的 Linux Docker Engine；包内 Compose 不代表包含 Docker Engine。
- 升级：指定实际实例 root、Compose project、包外 `target.env` 绝对路径及新候选/registry；升级器默认只读预检。只有本次明确授权升级 apply 后才执行 apply。仅支持升级器明确支持的变更；配置/schema/外置补丁/TLS 模式迁移若不受支持，停止并设计单独审查路径。
- 变更前按受控部署工具要求备份数据与数据库一致性快照，记录当前 image ID、秘密、证书/CA、配置、卷和恢复位置。保留无关服务和宿主数据；不要备份/清理之外的资源，不轮换或覆盖秘密，不在聊天输出秘密。

## 阶段五：部署、验收与停止处理

1. 按已核验、获授权的首装或升级路径执行受控安装/更新工具，不临时手工绕过校验、宿主检查或 Compose 差异门禁。执行前再次比对目标指纹、origin、TLS 模式、候选摘要；发生变化立即停止。
2. 失败时保留现场、日志、备份与旧 image ID；不自动清卷、删除旧包、重复首装或盲目回滚。仅按明确授权和受控恢复程序操作，并清楚报告当前服务状态及下一步人工决策。
3. 按授权验收：TLS 证书链、SAN、有效期和 HTTPS origin；健康接口/HTTP 状态；登录认证与 JWKS（如适用）；Web/客户端连接、Prosody/Jicofo 信令；Electron 与 Android 安装/启动；并强制验证非 P2P 通话实际经过 JVB，P2P 成功不算媒体通过。分别报告未测、失败、通过；静态检查、workflow 成功或容器运行不能替代真实端到端媒体证据。
4. 把证据关联到共同 `rN`、源码 SHA、配置 SHA、Run/attempt、Release、镜像 digest、目标身份和 TLS/origin。报告分阶段状态：构建、发布、部署、TLS/接口/客户端/信令/非 P2P 媒体；只有全部请求范围内项目均有证据才称完整交付。未请求的阶段标记“未执行”，不可暗示通过。

## 必须停止并报告的情形

- 远端/本地配置无法安全同步，或存在未解决的并发工作、身份不明、秘密暴露风险。
- 批准的 TLS 模式、HTTPS origin、架构、material commit、源码身份、分配记录或证据不匹配/缺失。
- 构建 job 失败、旧 attempt 混入、发布清单/摘要/digest 校验失败，或授权没有覆盖下一阶段。
- 目标主机、实例类型、目录、project、TLS 状态与请求不符；升级工具拒绝变更；目标数据备份或恢复前提不成立。
- 需要删除/覆盖数据、证书/信任根迁移、密钥/签名身份变更，或任何超出明确授权/受控工具能力的操作。

停止时说明已完成的最后阶段、精确失败项、保全的证据/恢复位置、真实影响和仍未执行的阶段；不自行扩大修复范围。

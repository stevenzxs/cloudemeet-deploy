# CloudMeet 编译、打包、部署统一规范（唯一规范源）

## 1. 效力与执行责任

本文件独立、完整地规定本工作区 CloudMeet 服务端及客户端的编译、打包、发布、安装、更新、验收与回滚规则。执行者必须遵守，不得通过新增脚本、改变架构、改用技能或测试拓扑规避。获得完整规范不需要阅读其他文档；不得把本文件未写明的强制要求委托给其他文档。

README 仅导航材料和报告实际状态；技能仅提供操作方法；检查脚本中的路径清单仅登记实现；包内 INSTALL 仅描述该包的实测操作；测试提供验证证据。它们都不是并列规范源，不得新增、放宽或覆盖本文件的要求。发现实现与本文件冲突时停止受影响步骤并报告，不能自行选择较宽松规则。根级安全、授权和环境保护要求仍须遵守。

## 2. 批次范围与授权

- 开始一次批次时记录目标 OS、架构、完整 origin（协议/主机/端口）、媒体地址与端口、安装路径、源码或镜像来源、服务/补丁/客户端范围及终点。复用已确认选择，不反复询问。
- 七服务为 gateway、app-web、api、web（Jitsi）、prosody、jicofo、jvb。不得用“七镜像构建成功”代替完整产品配置。
- amd64、arm64 共用产品要求；架构差异限镜像、工具、依赖及经验证的平台参数。不能默默关闭鉴权、丢弃品牌或角色能力。缩减功能的测试包必须获得明确范围授权，不得当作正常产品交付。
- 仅执行用户要求的里程碑，整批验证，不每小步停下。不得顺带整改广泛 CVE、升级依赖/锁文件、清理缓存或执行无关服务器操作；风险单列，遇具体阻塞或新授权边界才询问。

## 3. 目录与唯一流程

- `deploy/` 是唯一交付根，新目录统一为 `debug/<架构>/` 和 `release/<架构>/`，架构名称使用 `amd64`、`aarch64`。debug 用于功能迭代、bug定位与回归测试；release 用于正式部署交付。这是用途分类，不等同编译器 Debug/Release 模式，debug 包也可以正式签名或优化编译。
- `debug/<架构>/server/` 放服务器测试包，`clients/` 放客户端测试包，`evidence/` 放构建、诊断、回归及历史证据。`release/<架构>/server/` 放完整部署包，`clients/` 放客户端交付包，`dependencies/` 放 Docker、Compose 等依赖安装材料。
- 架构按产物本身而非其连接的服务器划分。客户端注明 OS/ABI；多ABI包记录实际支持集合，不冒称单架构。依赖在 dependencies 下按目标OS/版本和组件版本区分，记录来源、摘要、安装前提及验证状态；有安装材料不等于该平台安装通过，不授权覆盖已有引擎。
- 迁移现状：上述目录及 `config/` 已建立但仍为空；旧 `packages/`、`history/`、`artifacts/`、`releases/`、根 `clients/` 和 `offline-packs/` 尚未移动，现有工具仍可能输出旧路径。不得声称已改造工具或已迁移，不自动删除旧目录；用户后续人工清理。新批次采用新目录前必须显式核对工具的实际输出，尚未适配则报告差异，不能声称输出已在新目录。
- `config/` 用于人工维护公共配置，现有 `artifacts/nginx.conf` 尚未迁入；旧 `releases/` 为镜像候选登记、`offline-packs/` 为既有引擎材料，均不是另一条正式交付主线。
- `patches/` 是公开补丁维护源；`artifacts/` 是模板所需生成物暂存及路由配置；`tools/`、`tests/` 是维护工具和测试；`.worktrees/` 是独立 Git 工作树，不随整理移动或清除。
- 编译和组包工具留在 `build-tools/`；服务器构建/组包的位置按第4节已确认执行路线，不能默认改用WSL。WSL仅承担已授权的辅助脚本/测试与文件检查；Windows构建客户端。不得移动业务源码进deploy，不重建根级delivery-history或cloudmeet-deploy-offline。
- 根级 init.py、start.sh、Compose 是过渡模板，不是通用离线包；未更新全部调用与测试前保留位置。不得对离线安装套用在线 pull 流程。
- `build-tools/offline-runtime/` 是公共安装核心的收敛目标，尚非全部平台自动合格。禁止按架构新增独立精简产品安装逻辑。新增/替换入口必须登记调用关系、适用范围及测试，并证明继承全部产品要求；登记本身不放行。
- `build-tools/kylin-arm64/install.py` 与 `assemble-kylin-arm64-wsl.py` 因漏装产品补丁和 no-auth 配置，当前禁止继续产品交付；保留用于诊断。ARM CI 的 no-auth 控制面拓扑不得升级为产品运行基线。修复必须新建批次，不能靠改状态字段恢复资格。
- `packages/**` 及历史批次字节、日志、签名、摘要、旧路径不可原地修改。保留 old_deploy、openeuler-arm-deploy，不在整理时清理。现有包保留其限定平台和范围的历史证据，不因新登记升级资格。

### 3.1 人工维护目录及文件职责清单

下列路径均相对 `deploy/`。本清单直接说明职责，不把其他文档作为补全规范的前置阅读。新增、改名、迁移人工维护的文件或目录时，必须同步更新本清单与调用测试；不得先创建另一条部署线后补登记。

**枚举边界：**人工维护的脚本、配置、补丁、说明、技能及测试逐文件列明。编译生成物、下载的二进制、缓存、Git 内部文件、历史批次生成内容不逐文件枚举；只定义所在目录的职责和保护边界，不要求预知未来产物名称。生成文件不能反过来充当新的规范源。

#### 根目录文件与特殊目录

| 路径 | 作用 |
|---|---|
| `AGENTS.md` | 本文件，编译/打包/部署唯一完整规范源 |
| `README.md` | 材料入口、批次路径及实际状态导航，不另立规则 |
| `.gitignore` | 维护仓库跟踪白名单，排除产物、实例秘密和数据；不得强制添加绕过边界 |
| `SHA256SUMS` | 已有根级材料的校验清单，不代表所有未来包的完整性或产品资格 |
| `Caddyfile` | 根模板的 IP HTTPS 私有 CA、业务/会议路由与内部接口隔离配置 |
| `docker-compose.yml` | 根模板网关、业务 Web/API 与 Jitsi 配置覆盖，不能单独当完整配置 |
| `jitsi-base.yaml` | 根模板 Jitsi web、Prosody、Jicofo、JVB 服务定义 |
| `jitsi.env` | 根模板非秘密 Jitsi 参数、资源与内部管理配置 |
| `client.env.example` | 客户端专用 origin 参数示例，不放服务端秘密 |
| `init.py` | 根模板首次初始化目录及随机秘密，拒绝覆盖既有实例配置 |
| `start.sh` | 根模板准备补丁/权限、校验并启动服务，不隐式拉取或清数据 |
| `.git/` | 部署维护仓库 Git 元数据，不作交付材料、不手工整理内部文件 |
| `.worktrees/` | 独立工作树及其分支实现，不移动、不按缓存删除，不枚举内部副本 |
| `debug/` | 功能迭代、定位问题及回归测试材料根，不是正式交付入口 |
| `debug/amd64/`、`debug/aarch64/` | 按产物实际架构组织测试材料 |
| `debug/amd64/server/`、`debug/aarch64/server/` | 服务器测试包及镜像候选 |
| `debug/amd64/clients/`、`debug/aarch64/clients/` | MSI/APK等客户端测试包，记录实际OS/ABI |
| `debug/amd64/evidence/`、`debug/aarch64/evidence/` | 构建日志、诊断、回归和历史证据 |
| `release/` | 正式部署交付根；移动到这里不能替代资格验证 |
| `release/amd64/`、`release/aarch64/` | 按产物实际架构组织正式交付 |
| `release/amd64/server/`、`release/aarch64/server/` | 完整服务器部署包，按批次保存，不原地改包 |
| `release/amd64/clients/`、`release/aarch64/clients/` | 具备对应范围验收证据的客户端交付包 |
| `release/amd64/dependencies/`、`release/aarch64/dependencies/` | Docker/Compose等依赖安装材料，细分OS/版本，不自动安装 |
| `config/` | 人工维护公共配置的目标位置，当前未迁入旧配置 |
| `packages/` | 待人工整理的既有不可变服务器交付批次，不再作为新布局目标 |
| `history/` | 待人工整理的既有构建/实例/测试及技能备份证据；工具尚可能使用 |
| `clients/` | 待人工整理的既有客户端候选/交付材料，非新布局目标 |

#### 模板生成物、引擎材料与入口登记

| 路径 | 作用 |
|---|---|
| `artifacts/` | 根模板的业务生成物暂存及人工维护路由配置；JAR/dist 等编译结果不枚举 |
| `artifacts/nginx.conf` | app-web 的静态页面、业务 API 代理路由配置 |
| `offline-packs/` | 既有离线引擎依赖材料，不是完整产品包 |
| `offline-packs/ky10-arm64/` | 麒麟 ARM64 既有 Docker 材料；下载的 Docker tgz 不逐项登记 |
| `offline-packs/ky10-arm64/install-docker-offline.sh` | 既有 Docker 离线安装脚本；运行有宿主变更，不因目录检查授权执行 |

#### 补丁维护源

| 路径 | 作用 |
|---|---|
| `patches/` | 服务器公开补丁维护源，非架构专属复制品 |
| `patches/README.md` | 已有补丁文件及运行验证方法说明，非独立规范 |
| `patches/web/` | 会议页面品牌、CSS 注入和可选主持人菜单配置 |
| `patches/web/custom-interface_config.js` | 品牌名称、水印及推广界面配置 |
| `patches/web/custom-head.html` | 页面 head 注入片段，关联自定义 CSS |
| `patches/web/custom.css` | 会议界面样式覆盖 |
| `patches/web/host-control-custom-config.js` | 按能力开关生成主持人转移等自定义菜单配置 |
| `patches/web/nginx-custom/` | Jitsi web 自定义 Nginx 路由片段 |
| `patches/web/nginx-custom/custom-css.conf` | 将 CSS/head 请求映射到实际运行配置目录 |
| `patches/prosody/` | XMPP 角色及可选转移插件 |
| `patches/prosody/mod_muc_jwt_owner.lua` | 普通 JWT 主持人到 MUC owner 的角色映射 |
| `patches/prosody/mod_muc_host_transfer.lua` | 可选主持人转移、业务角色确认与权限变更插件 |
| `patches/prosody/HOST-TRANSFER.md` | 主持人转移已有实现的来源、安装、验证和回滚操作说明 |
| `patches/optional-http/` | 仅用于批准 HTTP 模式的条件补丁，不属于 HTTPS 默认配置 |
| `patches/optional-http/README.md` | HTTP 补丁适用场景和操作说明 |
| `patches/optional-http/external_api.js` | 既有 external API 的 HTTP iframe 协议适配副本；虽为大型 JS，属于维护补丁而非本批编译输出 |

#### 维护工具与测试

| 路径 | 作用 |
|---|---|
| `tools/` | 已有部署维护工具，不是新的整栈安装入口 |
| `tools/check-deployment-layout.py` | 内含现有实现路径清单，只读校验限定命名入口是否登记，不执行部署、不新增规范 |
| `tools/assemble-aarch64-product.py`、`tools/aarch64-product-inputs.py`、`tools/offline-runtime/` | Actions所需build-tools维护源的受控同步副本；只在runner组包/校验，不另建安装逻辑；每批核对源与副本摘要 |
| `tools/product-inputs.json` | 本批Actions输入文件摘要，锁定公开补丁、配置与公共运行时副本；不是运行验收结果 |
| `tools/verify-aarch64-product-runtime.py`、`tools/product-role-probe.py` | build-tools同名源的受控CI副本；严格TLS下核对外置补丁实际资源和真实BOSH/JWT角色，不等于全系统离线首装 |
| `.github/workflows/aarch64-product.yml` | CI分支原生aarch64候选组包入口，只有只读仓库/artifact权限，不上传服务器或发布镜像 |
| `tools/fetch-image.py` | 从 registry 获取 ARM64 镜像，校验层摘要并导出 Docker 归档 |
| `tools/backup-host-control.py` | 主持人能力更新前检查会议空闲并创建配置/SQLite 一致性备份 |
| `tools/prepare-host-control.py` | 准备可选主持人能力覆盖配置与秘密，不自动部署或重启 |
| `tools/stage-host-control.py` | 核实插件摘要并准备插件、内部 Caddy 配置，不重启 |
| `tools/stage-host-control-web.py` | 校验业务 Web 归档并准备目录覆盖候选，不替换数据或镜像 |
| `tools/fix-host-control-mount.py` | 修正既有候选 overlay 的 Prosody 配置挂载路径，属于写操作 |
| `tools/enable-host-control.py` | 通过前提检查后显式打开候选能力配置，不自动重启 |
| `tools/probe-host-control.py` | 通过临时容器探测内部严格 TLS/鉴权，不打印秘密；并非纯静态检查 |
| `tools/inspect-host-control-state.py` | 只读查询 SQLite 角色状态/操作数量，不输出凭据 |
| `tests/` | 已有维护功能回归及历史专项交付记录，不代表全产品验收 |
| `tests/test_host_control_prepare.py` | 准备步骤拒绝覆盖、配置及秘密处理回归 |
| `tests/test_host_control_enable.py` | 启用前会议空闲和前置条件等拒绝路径回归 |
| `tests/test_host_control_web.py` | Web 候选摘要、解包和防覆盖回归 |
| `tests/host-menu.test.cjs` | 自定义菜单能力开关及重复应用回归 |
| `tests/prosody-host-control-tls.lua` | 在实际 Prosody 中探测内部 API 严格 TLS 及鉴权 |
| `tests/HOST-TRANSFER-DELIVERY.md` | 2026-11-10 主持人转移专项历史范围/交付记录，不是当前通用规范 |

#### 镜像候选登记与技能维护材料

| 路径 | 作用 |
|---|---|
| `releases/` | 镜像候选版本的人工登记；生成镜像/归档不逐项枚举 |
| `releases/11248-cm.20261110-rc2-amd64/` | 已有 amd64 候选版本登记，不是通用产品包 |
| `releases/11248-cm.20261110-rc2-amd64/README.md` | 该候选来源与已知状态说明 |
| `releases/11248-cm.20261110-rc2-amd64/registry.yaml` | 该候选七服务 registry 镜像身份锁定清单 |
| `skills/` | 两个部署技能的唯一维护源；仅提供操作方法，不新增规范 |
| `skills/cloudmeet-deploy/` | 服务端部署、更新和客户端交付操作技能 |
| `skills/cloudmeet-deploy/SKILL.md` | 技能触发及操作流程说明 |
| `skills/cloudmeet-deploy/evals/` | 部署技能触发/流程评估输入 |
| `skills/cloudmeet-deploy/evals/evals.json` | 部署技能评估用例，不等于产品回归结果 |
| `skills/cloudmeet-deploy/references/` | 部署技能操作参考资料 |
| `skills/cloudmeet-deploy/references/arm-clients.md` | ARM 场景与客户端构建操作参考 |
| `skills/cloudmeet-deploy/references/delivery-documents.md` | 交付报告、硬件/端口及报价等材料编写方法 |
| `skills/cloudmeet-deploy/references/ghcr-images.md` | GHCR 镜像候选获取与核验方法 |
| `skills/cloudmeet-deploy/references/server-202.md` | 202 实例的历史排坑资料，不是默认部署目标 |
| `skills/cloudmeet-deploy/references/services-and-patches.md` | 服务依赖、补丁选型与验证方法参考 |
| `skills/cloudmeet-deploy-offline/` | 离线材料获取、组装和验证操作技能 |
| `skills/cloudmeet-deploy-offline/SKILL.md` | 离线技能触发及操作流程说明 |
| `skills/cloudmeet-deploy-offline/evals/` | 离线技能评估输入 |
| `skills/cloudmeet-deploy-offline/evals/evals.json` | 离线技能评估用例，不等于安装通过证据 |
| `skills/cloudmeet-deploy-offline/references/` | 离线技能操作参考资料 |
| `skills/cloudmeet-deploy-offline/references/bundle-spec.md` | 离线包布局和材料组织方法参考，非并列规范 |
| `skills/cloudmeet-deploy-offline/references/image-inventory.md` | 镜像材料收集与来源核对方法 |
| `skills/cloudmeet-deploy-offline/references/patches.md` | 离线补丁装配及验证方法参考 |

未来编译输出目录、缓存目录（如 `__pycache__/`）、归档、镜像层、日志和批次报告按本文件既有归属及保密规则处理，不因未逐项列名而禁止正常生成；不得借此豁免新增人工维护脚本或配置的职责登记。

## 4. 源码编译与来源

### 4.1 构建平台与职责（不得隐式切换）

- 本次47 aarch64交付及其后续镜像发布：服务器源码编译、镜像构建、补丁集成回归、镜像导出、部署包组装及包级校验统一在 **GitHub Actions原生aarch64 runner** 执行。工作流须校验并记录runner实际架构、run ID/attempt、workflow与部署材料提交、每个源码提交。amd64批次使用明确选定的匹配平台；未确认路线不得自行推断。
- 本机只编辑维护代码、运行无需Docker的辅助回归、调度/查询Actions、下载校验及整理产物，以及构建和真机测试客户端。本批不在本机启动Docker Desktop/daemon、加载/运行服务器镜像或用本机WSL重建/组装服务器包。确需改路线时说明原因、影响和替代验证，取得用户明确同意；本机没有Docker不是Actions构建的阻塞。
- Actions中运行Docker是runner内的构建/测试步骤，不等于允许本机使用Docker。原生runner上的容器集成测试仍不等于独立全系统离线首装；达不到第6节证据要求时如实阻塞，不在本机补一套然后冒称通过。
- 47由用户人工上传并执行包内脚本；代理不执行远端清理/上传/安装。部署后Android/Electron真机回归在本地连接目标。第一阶段约定回归全部通过、发现的阻断bug关闭后，才允许Actions发布对应已验镜像，不能提前推送或用重建镜像替代已验字节。

### 4.2 来源记录

- “当前源码构建”指使用现有工作区相关应用源码，允许在线取得公开依赖、基础镜像与工具；不要求从源码编译全部传递依赖。不得静默替换为预构建应用镜像。
- 每组件记录源码 commit、dirty 状态及实际变更身份、依赖/基础镜像身份、构建结果和产物摘要。保留原 env、锁文件及用户改动，临时配置须恢复。不得混用不同批次而隐去来源。
- 镜像逐项核实实际 image ID/digest、OS/architecture、归档大小和 SHA256；不能仅信文件名或 manifest 声明。来源、架构或必需依赖缺证据即阻断该项交付。

## 5. 补丁与产品配置（所有架构必检）

### 5.1 deploy/patches进入Actions及交付的完整链路

- **唯一补丁维护源是当前部署维护仓库的 `patches/`（工作区路径 `deploy/patches/`）。**Actions看不到Windows工作区路径；不能写一条D盘COPY就声称已使用本机补丁，也不能仅checkout业务源码后假设补丁自动存在。
- 调度前核对当前补丁文件清单及SHA256、Git dirty状态。Actions的输入必须锁定包含本批补丁的部署维护仓库完整commit SHA；未提交/未推送的本机改动不会自动进入runner。必须先经审核将所需变更纳入远端可取得的确定提交，记录该SHA；无发布/推送授权或材料无法取得时报告阻塞，不用旧远端版本继续。若另行批准不可变输入artifact传递，须记录来源commit/差异、artifact ID和独立可信SHA256，并按同等要求验证，不能隐式切换。
- 工作流显式checkout该部署材料SHA到独立目录（例如runner的deployment-input），从其中的 `patches/` 取材；各业务源码单独锁定自己的SHA。若workflow从另一个分支/worktree运行，必须显式指定材料SHA，不能继承该分支的陈旧补丁。runner核对实际checkout SHA及逐文件摘要与调度输入一致后才继续；缺项或不一致立即失败。
- 所有补丁逐项确定两种承载方式之一：①**外置交付**：从deployment-input/patches复制到包内patches，由公共安装步骤复制到持久配置目录，Compose正确挂载并配置模块/引用；②**镜像内置**：显式复制到相应Docker build context（COPY不能越出context），Dockerfile安装到已确认加载路径，记录产物镜像及运行文件摘要。每项只选有证据的方式，不能用“源码镜像”推断已内置，不适用项必须有理由。
- 必需的品牌配置、CSS/head/Nginx映射、JWT角色插件及其配置必须完整覆盖。Actions既检查最终归档实际成员/摘要及渲染Compose，也启动最终导出的同批镜像验证页面引用、资源200/摘要、插件实际加载、真实JWT角色；只cmp源码或Lua语法检查不算应用成功。
- 构建job、集成job、组包job显式传递同批不可变artifact与补丁材料；记录run/attempt、artifact ID、归档SHA256、镜像manifest/config身份和补丁来源SHA。后续job下载后重新校验，不重新checkout浮动main或用另一次构建的latest补缺。
- 必须通过真实组包/安装检查入口执行坏包负例：从最终候选删除CSS、head、Nginx映射或JWT插件，取消引用/模块加载、关闭鉴权，均应拒绝或导致对应验收失败。负例只操作独立测试副本，不修改原始产物；测试预期不能从候选自声明清单生成。未覆盖的环节明示未完成。
- 部署后按同批补丁清单核对目标运行文件摘要、实际加载和产品行为。第二阶段镜像发布复用已验镜像；外置补丁、初始化及配置必须作为同版本配套部署材料一起交付，其他服务器仅docker pull不足以完成部署。不得带47固定origin/秘密/CA私钥，入口通过目标实例参数配置。

### 5.2 每批补丁适用性与运行要求

- 每批对补丁逐项记录来源版本/摘要、适用条件、安装目标、权限、加载配置、回滚点及验证结果。每项必须结论为“安装”“已内置且有证据”或“有理由不适用”；缺结论阻断。不能一律全复制，也不能一律忽略。
- 品牌补丁为 `web/custom-interface_config.js`；CSS 注入必须成套处理 `web/custom.css`、`web/custom-head.html` 和 `web/nginx-custom/custom-css.conf`，验证实际引用、HTTP200、摘要和视觉结果。
- 普通 JWT 主持人映射使用 `prosody/mod_muc_jwt_owner.lua` 或经行为验证的等价内置实现；验证实际模块加载，关闭 Jicofo 自动 owner，实际确认主持人 OWNER、普通成员 PARTICIPANT。JWT app ID/secret/内部域配置必须一致，不能用关闭鉴权或自动授予 owner 替代。
- 主持人转移是独立可选能力，不默认开启；启用时须完整验证密钥轮换、撤权、接收确认与恢复，不能用仅装菜单或普通 moderator 授权代替。HTTP iframe/信令降级仅适用明确批准的 HTTP 模式，不加入 HTTPS 默认基线。
- 补丁公开目录典型0755、文件0644；仅修正必要公开范围。Prosody storage 属主必须与所选镜像 UID/GID 一致，不能盲用1000。宿主文件存在或单元测试通过不证明容器已加载。
- 最终包检查必须独立依据产品要求检查缺失，不能只核对组包器自己生成的文件列表。必须有删除补丁、取消引用/模块加载、关闭必需鉴权等坏包负例；坏包仍通过则门禁无效。

## 6. 离线组包与安装资格

- 组装阶段明确标为未完成候选。最终包需含全部适用配置/补丁、安装工具、同平台镜像、离线依赖、操作说明及校验材料；不含真实服务器 env、生产数据库、秘密或 CA 私钥。
- 构建机可联网，目标安装器必须只使用交付材料，不得临时下载补缺。默认 no-build、no-pull；需要已有 Docker 的包必须明确前置条件，不冒称包含 Docker 离线首装能力。
- 材料完整 ≠ 可安装 ≠ 目标已安装 ≠ 客户端/媒体通过。`READY_FOR_INSTALL` 必须有独立全系统离线环境、空镜像 store、原始初始化/启动入口的实际证据；范围含 Docker 首装时还须完成其离线首装。复用缓存、userspace 容器、单元测试不替代这些证据。
- 验证最终包的完整性、依赖闭包、镜像身份/平台、实际渲染 Compose、补丁安装/加载、严格 TLS/API/真实信令/可用桥。不得手改状态或使用 QA override 代替资格；QA override 留在交付外。
- 新布局完整服务器交付进入 `release/<架构>/server/<批次>/`，最终复制后复核所有摘要，报告实际路径、可信 SHA256SUMS 摘要、限定平台/origin、已过门禁和未验项。旧 packages 包保持原位置直至明确迁移；历史路径不能替代实际交付路径。
- 不断网、不移除已有 Docker/数据/CA 卷来模拟离线；在独立环境验证。

## 7. 目标部署、安全与回滚

- 本地整理/组包不授权 SSH、上传、重启、迁移、卸载或切换服务器。部署既有实例前核实其实际配置，不能用 IP HTTPS 模板覆盖 ARM HTTP 或域名/DNS 插件实例。
- 破坏性操作前须只读盘点、验证恢复备份，列出准确目标、待删除和保留资源及风险，取得 explicit second confirmation（二次明确确认）。禁止全局 prune、无范围 down -v、清防火墙、网桥、无关 VPN/代理或新增宿主 Docker daemon。
- 保留数据库、会标、秘密、CA 卷和无关服务；SQLite 一致性备份，不能复制写入中的 DB 冒充可恢复备份。更新只变更批准的服务范围。
- origin、PUBLIC_URL、iframe 与信令路由必须一致，端口按实例批准值，不默认占80/443；JVB advertise 为真实可达媒体地址，内部管理端口不公开。检查 SSI/静态路由、内部接口隔离及 WebSocket 后的实际 XMPP 会话。
- Caddy 私有 CA 保留服务端私钥及卷，只分发公开根；严格校验链、主机、时效，实测 IP 无 SNI 路径，不 pin 会轮换的叶证书，不全局绕过 TLS。
- 回滚保存本实例旧配置/补丁/镜像身份和一致性数据备份，评估数据库兼容；不能覆盖更新后的用户数据或无故换证书/秘密。恢复后重新验证数据、接口和会议。

## 8. 客户端编译、签名与验收

- 唯一 release 构建入口为 `build-tools/clients/build-clients.cjs`，显式指定仅含 SITE_DOMAIN、SITE_SCHEME、SITE_PORT 的 client-only env。唯一活动版本状态为 `build-tools/clients/release-version.json`，不绕过计数、不回退已占版本、不并发构建或删除活动锁。
- 每批核对完整 origin、实际 MSI/APK 版本和摘要、包内入口及目标公开 CA。新地址不会自动配置 CA 信任。Electron 按准确 origin 限定信任；Android 按主机限定，保留已有端点策略，不打包私钥。
- 实测 APK signing certificate、MSI/内嵌程序实际签名与有效性；旧 manifest 固定文案和文件名不是签名证据。签名改变字节后重新计算最终摘要。
- 客户端新布局为先进入 `deploy/debug/<架构>/clients/<批次>/`，接受交付进入 `deploy/release/<架构>/clients/<批次>/` 并明示状态；当前构建器仍输出 `deploy/history/client-builds/`，未完成路径适配，必须据实报告。本次目录创建不授权改动构建器。设备安装需授权并保留数据，Android 使用数据保留升级，不自动卸载旧版或清数据。
- 安装成功、首页、入会、真实媒体分别取证。至少三端或关闭 P2P 确保经过 JVB，核对 ICE/UDP、双向音视频、共享及重连；未验证不能标通过。no-auth 同会不能证明 JWT 角色或转移能力。

## 9. 测试、记录及能力边界

- 在工作区根执行只读布局检查：`python -B deploy/tools/check-deployment-layout.py`；治理回归：`python -B -m unittest discover -s build-tools/migration -p test_deploy_governance.py`；目录回归：`node --test build-tools/migration/client-layout.test.cjs`。
- Linux 安装测试在 WSL 执行：`wsl -d Ubuntu-24.04 -- python3 -B -m unittest discover -s /mnt/d/code/jitsi/build-tools -p "test_offline*.py"`。这些测试依赖 POSIX，不用 Windows 结果代替。包复制/迁移后执行包内实际提供的只读校验入口（如 install.py --verify-only），不为文档验证运行安装/部署命令。
- 布局检查只识别 deploy/build-tools 中规定命名的入口/Compose，不检测任意改名脚本、嵌入命令或 worktree；尚未接 CI/分支保护，不能阻止直接运行旧脚本。公共安装核心、独立产品契约校验及包级负例门禁尚未全部完成，不得声称不可绕过或全平台已统一。
- 逐项报告通过/失败/阻塞/未验证与证据，不给虚构百分比，不把安装资格当生产安全或媒体验收。未解决 CVE 不标已接受。
- 唯一当前执行记录位于 `build-tools/migration/STATUS.md`；历史记录不作当前运行事实或继续授权。
- 技能维护源仅 `deploy/skills/cloudmeet-deploy/` 和 `cloudmeet-deploy-offline/`；同步前备份，仅更新这两个安装副本并核对摘要。技能不得成为另一份规范，不编辑无关技能或设置。

# CloudMeet 部署资料统一入口

编译、打包、部署的完整统一规范唯一由 [AGENTS.md](AGENTS.md) 负责，无需跳转其他文档补全规则。本页仅作材料导航和状态说明，不是第二份规范。本目录不是一个可以直接上传启动的通用产品包。

## 先选材料身份，不选另一条部署线

编译打包仅含：确认批次 → 编译/复用 → 组包 → 材料完整性校验 → 输出release包。不要求测试环境、麒麟ISO或安装运行测试；包不含宿主操作系统。流程及流程图见AGENTS.md第6节，不表示安装器/工作流已经适配或已有新包。

“打包release”以实际包、完整材料、摘要校验和本地路径交付为终点；不将后续测试作为出包条件。安装器仍只会REFUSED属于实现缺陷，不能隐去或靠篡改状态解决。

### 唯一新增交付布局

```text
deploy/
├─ release/
│  ├─ clients/<架构>/<批次>/       # 客户端独立交付根，注明OS/ABI
│  ├─ amd64/{server,dependencies}/
│  └─ aarch64/{server,dependencies}/
└─ config/
```

只交付release：server放编译组包及材料完整性校验通过的完整包（不要求安装测试），clients按自身OS/ABI和已验范围交付，dependencies按OS/版本分类。未完成候选保留在Actions；完整包附材料校验及来源证据。config是人工公共配置目标位置。

### 统一Actions入口（2026-11-11脚本优化）

- 维护源：`../build-tools/build-package.yml`、`../build-tools/package.sh`；CI入口：`.github/workflows/build-package.yml`。
- 手动指定版本及受审材料commit，原生aarch64矩阵完整编译七服务，再仅收集同run/attempt镜像组包；不回退旧镜像。
- 统一版本下分别记录源码commit、真实镜像ID、基础镜像及归档摘要；包内携带Compose和公共首次安装核心，已有Docker为明确前提。
- 本轮为本地脚本优化，尚未推送或运行新的Actions，没有新部署包；安装/服务/客户端/媒体均未因此验收。旧workflow保留手动诊断，不自动push触发。
- 业务Web本批使用same-origin构建参数，工作区默认118 `.env`不变；包内记录实际覆盖。用法见`../build-tools/README.md`。

用户已授权删除debug及全部候选/证据，不迁移到release。原有packages、history、artifacts、releases、clients、offline-packs保留原位，不在本次清理范围。工具输出尚未全面适配；下方旧路径仅导航历史材料。编译、打包、部署要求仅由AGENTS.md负责。

| 需求 | 查找位置 | 限制 |
|---|---|---|
| 已验证服务器包 | `packages/<批次>/INSTALL.md` | 仅按包内限定的系统、架构、origin 与验收状态使用 |
| 构建/实例证据 | `history/` | 不是默认安装入口，不改历史字节 |
| 镜像候选 | `releases/` | 不是离线安装包 |
| 客户端构建 | `../build-tools/clients/README.md` | 输出先进入 history，按实际验收状态交付 |
| 补丁和实例增量 | `patches/`、`tools/`、`tests/` | 不替代完整产品部署 |
| 安装器/组包器维护 | `tools/check-deployment-layout.py` 内的实现清单 | 登记不等于放行，规范仅在 AGENTS.md |

**2026-11-11 风险隔离：**`../build-tools/kylin-arm64/install.py` 与 `assemble-kylin-arm64-wsl.py` 漏装产品补丁，使用 no-auth 基线，禁止继续作为产品交付路径。旧包与七镜像构建证据保留；构建通过不代表产品部署一致。跨架构公共安装核心尚未完成，不能宣称已统一运行逻辑。

## 源码版本管理

七服务 GHCR 候选发布：[11248-cm.20261110-rc2-amd64](releases/11248-cm.20261110-rc2-amd64/README.md)（主持人转移修复；镜像锁定清单，不是离线安装包）。

部署维护仓库：<https://github.com/stevenzxs/cloudemeet-deploy>。
本仓库仅追踪模板、初始化/启动脚本、公开补丁、技能、测试及维护文档；
`history/`、`packages/`、`clients/`、实际实例配置、数据库、密钥和构建产物保留本地，不上传Git。
忽略规则采用根目录白名单，新增维护文件须显式审核纳入。不要使用 `git add -f` 绕过秘密或产物边界。
本文及技能中的工作区相对路径描述多仓库布局；单独克隆本仓库不会自动获得相邻源码、构建工具或历史交付包。
补丁修改需与测试、部署说明一起提交，发布证据记录提交ID及实际产物摘要；源码提交不代表部署或媒体验收完成。

> 本页仅作导航，唯一规范是AGENTS.md。新增交付只用release；旧材料未迁移。服务器编译组包沿用已确认Actions原生aarch64路线，本机不使用Docker。下方根级模板流程不是离线包安装入口。

```text
deploy/
├─ packages/   完整可安装服务器包（不可原地改包）
├─ clients/    MSI/APK，以各批实际验收状态为准
├─ history/    原 delivery-history，完整保留历史字节
├─ skills/     cloudmeet-deploy 与 cloudmeet-deploy-offline 维护源
└─ 根级配置/patches/artifacts/tools/tests：现有模板与工具，暂保留位置
```

根级 `delivery-history/` 与 `cloudmeet-deploy-offline/` 已归入本目录，不再新建。历史日志/包内旧路径保留原样，仅更新活跃工具和文档。模板进一步分层须单独验证所有调用，不在本次整理中顺带迁移。

## 已验证的离线服务器包（2026-11-09）

实际安装包目录：[`packages/cloudmeet-server-115-amd64-20261109T091403524280Z/`](packages/cloudmeet-server-115-amd64-20261109T091403524280Z/README.md)。完整目录复制到目标机使用，不是 MSI/EXE；安装入口是包内 `engine.py` 和 `deploy.py`，详见包内 `INSTALL.md`。
独立留存副本保留在 [`history/`](history/offline-bundles/20261109-115-amd64/cloudmeet-server-115-amd64-20261109T091403524280Z/README.md)，不覆盖现有部署配置。
可信渠道核对 `SHA256SUMS` 的 SHA256：`6fc01c791c21a6b39574a7c9e1eec3a3f98683a4782d82ca38de305e38f8bac3`。
状态 `READY_FOR_INSTALL`，限 Ubuntu 22.04 amd64、固定入口 `https://115.190.243.21`。
已在独立全系统 VM 完成无外网 Docker 首装、空缓存七镜像导入、原安装器启动和严格 TLS/API/BOSH/WebSocket/可用桥验收。
按该包 `INSTALL.md` 执行，不使用本页下方在线 `pull` 流程；本 `deploy/` 工作树仍处于迁移中，未被覆盖。
115旧实例的备份和精确清理确认、目标新CA专属MSI/APK、多端双向音视频仍待完成；已记录安全风险未解决，安装资格不等同生产安全放行。

`deploy/` 是工作区唯一部署资料入口。部署配置、启动脚本、补丁和操作说明均在本目录，不依赖其他历史部署目录。业务及客户端源码仍位于相邻源码项目，构建依赖不是历史部署依赖。

## 1. 实际文件

主持人转让为可选独立能力，普通JWT主持入会通过不代表转让可用。
源码提交、内部TLS/认证、持久菜单配置、回归及回滚步骤见
[转让部署手册](patches/prosody/HOST-TRANSFER.md)。默认模板不自动开启，
不得只安装菜单或只授予moderator来代替密钥轮换与撤权链路。

2026-11-10 jks 主持人修复客户端候选：
[`clients/jks-whclaw-top-android-1.0.17/`](clients/jks-whclaw-top-android-1.0.17/README.md)，
APK SHA256 `e1d8c6882a885fffae0babb3ff2c804a00bceeac1ad855e6e056f0627c5f043f`。
保留数据安装、双向产品转让、 persisted-pending recover/rebind、active-host
进程死亡重进与创建者产品收回已验；未收到私有回执前死亡的会话仍需创建者
收回。完整媒体与生产安全仍未验，不标为全产品发布放行。现有Electron1.0.9兼容。

| 文件 | 用途 |
|---|---|
| `config/docker-compose.yml` | 网关、业务 Web/API 以及 Jitsi 环境覆盖；必须在根基础配置之后合并 |
| `config/jitsi-base.yaml` | 官方 Jitsi Web、Prosody、Jicofo、JVB 四组件定义 |
| `config/jitsi.env` | Jitsi 非秘密配置、资源参数和私有管理端口 |
| `config/Caddyfile` | 无固定IP的HTTPS模板：本地私有CA兜底证书、通配路由、内部接口阻断，HTTP返回426 |
| `config/init.py` | 首次创建deploy根的数据目录和随机秘密，拒绝覆盖已有 `.env` |
| `config/start.sh` | 固定deploy项目根，复制持久补丁、校验并启动，不删除数据、不隐式拉镜像 |
| `patches/` | 品牌、CSS 和主持人角色插件的部署副本 |
| `artifacts/nginx.conf` | 业务 Web/API 路由配置 |
| `../build-tools/clients/` | MSI/APK 构建工具已迁出；不属于服务器交付材料 |
| `client.env.example` | 客户端专用入口模板，不携带服务端秘密 |
| `../build-tools/clients/tests/` | 客户端构建脚本测试，已迁出 |
| `skills/cloudmeet-deploy/` | 交互式部署技能维护源 |
| `skills/cloudmeet-deploy-offline/` | 离线打包技能维护源，与工作区规范共同读取 |

当前可执行基线是 **IP + HTTPS + Caddy 私有 CA**，业务代码由本地源码构建，Jitsi 使用官方镜像。基础镜像支持何种平台须检查 manifest；不是将本地业务 ARM 镜像当作通用包。域名公共证书、DNS-01、HTTP 测试需另行审查实例配置，不能把本基线称为已覆盖全部模式。

## 2. 过渡模板参考（不是通用安装入口）

以下命令仅解释根级模板原有调用关系。新交付必须使用上方包级入口及治理规范，不能直接照抄本节代替离线安装与产品验收。

### 参数与授权

先确认主机、SSH 端口、架构、入口/端口、部署路径、源码或镜像来源、全量或增量、服务与客户端范围。历史地址不是默认目标。

全量重置必须先只读盘点、完成备份，并集中展示目标、删除/保留清单和风险，取得二次明确确认；本目录不提供自动清空脚本。增量更新保留数据库、会标、秘密、CA 和未变服务。

### 准备业务产物

在相邻源码项目构建：

- API：`mvn -B test package`；复制本次 JAR 到 `artifacts/app.jar`。
- Web：使用现有 `same-origin` 配置构建，执行 `npm run build`、`npm run check:webview-syntax`；复制本次输出到 `artifacts/dist/`。保留源码项目原 `.env`，核对输出的实际入口。
- 本目录 `patches/` 是部署副本，源码变更后需主动同步并更新 SHA256，不能假定自动更新。

### 服务器初始化与校验

只上传本次配置、补丁及业务产物；不上传别的实例秘密、数据库、证书私钥或整个工作区。

```bash
# 在实际部署目录执行；仅首次初始化，参数为本次批准的 IP。
python3 config/init.py

# 所有操作使用同一组参数，不省略 -f 让未知 override 自动生效。
target_exports=$(python3 -B config/target.py config/target.env)
eval "$target_exports"
docker compose --project-directory "$PWD" --env-file config/jitsi.env --env-file .env \
  -f config/jitsi-base.yaml -f config/docker-compose.yml config --quiet
docker compose --project-directory "$PWD" --env-file config/jitsi.env --env-file .env \
  -f config/jitsi-base.yaml -f config/docker-compose.yml pull

# 先检查所有镜像实际架构、摘要及端口；再执行启动。
bash config/start.sh
```

七个服务：`gateway`（TLS/入口）、`app-web`（业务页面）、`api`（业务/JWT/SQLite）、`web`（Jitsi 页面/信令）、`prosody`（XMPP/角色）、`jicofo`（会议协调）、`jvb`（媒体）。本配置 `web` 不是业务 Web。

初始化不自动备份、删除旧资源或检查云安全组。`start.sh` 不是增量发布事务；更新前需单独准备备份、维护窗口及最小服务范围，避免无必要重启。

## 3. 补丁包

详见 [补丁说明](patches/README.md)。发布包必须有补丁版本/来源/适用条件、文件摘要、回滚点和验收结果，不包含数据库、秘密、CA 私钥或历史安装包。

当前包含：

- `web/custom-interface_config.js`：产品名、关闭水印及推广。
- `web/custom.css`、`web/custom-head.html`、`web/nginx-custom/custom-css.conf`：成套 CSS 注入。
- `prosody/mod_muc_jwt_owner.lua`：JWT 主持人角色，配合关闭 Jicofo 自动 owner。

当前 HTTPS 基线**不挂载** HTTP external API 补丁、不启用 HTTP 专用 BOSH 降级、不默认开启主持人转移插件。

## 4. 注意事项

- 公开静态/补丁目录须容器用户可遍历，典型为目录 0755、文件 0644。0700 上传目录曾导致页面 403、CSS 404 和品牌漏加载。不要递归放宽整个项目、秘密或备份权限。
- Prosody storage UID/GID 当前基线为 1000:1000；变更镜像须重新确认。运行配置位于 `/run/<service>/config`，宿主文件存在不代表已加载。
- TCP 80/443、UDP 10000 按实例放行；9000、5222、5280、2019 和桥/协调管理端口不公开。JVB advertise 使用真实可达媒体公网地址，而非 CDN/FRP 地址。
- `.env` 与备份权限受限。SQLite 用一致性备份或停 API 后备份，不随便复制写入中的 DB。
- Caddy `tls internal` 自动管理叶证书，必须保留 CA 数据卷。只分发公开根 CA，客户端限定主机信任且校验链、SAN、有效期；不能 pin 会轮换的叶证书或全局绕过校验。IP 无 SNI 场景由 `default_sni` 处理并需实测。
- 首次签发成功不代表续期实测完成；监控时间、证书到期与错误。域名还需确认 DNS、云接入备案及验证路径。
- GHCR 慢速不能靠 Docker Hub 加速器保证解决。可使用官方同平台同摘要离线镜像，核对传输完整性；不使用不明替代镜像。
- 禁止全局 prune、无范围 `down -v`、删除网桥、清空防火墙及删除无关 VPN/代理。已有服务空闲或批准维护后才重启。

## 5. MSI / APK

### 独立离线IP证书工具

证书签发、更新和回滚入口见[`cert/README.md`](cert/README.md)。可填写不同内网/外网IPv4，
在可信机器生成证书和脚本后人工上传服务器执行；不随文档操作自动连接服务器。
CA私钥仅留离线签发机，服务器私钥更新包须受限保管；客户端CA信任仍需另行适配。

Windows 下从工作区根目录构建，源码仍在 `jitsi-meet-electron/` 和 `jm/`：

```powershell
# 唯一入口配置：deploy/config/client.env；编辑其中host/scheme/port。
# 先执行只读检查；Android versionCode从CLIENT_VERSION自动转换。
node build-tools/clients/build-clients.cjs --target all --env-file deploy/config/client.env --check
node build-tools/clients/build-clients.cjs --target all --env-file deploy/config/client.env
node --test build-tools/clients/tests/*.test.cjs
```

唯一客户端入口配置为 `deploy/config/client.env`，当前为 `https://47.96.221.94:8443`。不从服务端配置、旧client.env、环境变量或源码默认值覆盖/回退。统一入口已恢复，Android versionCode自动从配置版本转换，无需历史证据，详见[工具说明](../build-tools/clients/README.md)。候选输出到本机Temp/opencode/cloudmeet-clients-*，不自动晋级交付；新客户端交付放入`deploy/release/clients/<架构>/<批次>/`，clients与amd64、aarch64同级。此前1.0.19-20261112-143033批次仍在原架构目录下的clients中，本轮仅改文档、未移动包。实际签名必须检查产物，不能信任固定文案。

发布版本唯一读取`deploy/config/client.env`的`CLIENT_VERSION`，当前填写`1.0.19`；Electron产品版本和Android versionName共用该值。Android versionCode按`major×1000+minor×100+patch`转换，本次为`1019`；minor限定0..9、patch限定0..99。相同版本得到相同code，不自动递增，不读取历史证据、时间计数或release-version.json。旧时间计数APK可能无法覆盖升级，提示但不阻止编译；不自动卸载或清数据。构建记录保留实际版本和versionCode。

构建器在构建期间向Electron package.json临时注入CLIENT_VERSION并恢复；Android用Gradle参数注入versionName和自动转换的versionCode，不改源码默认appVersion。不得绕过统一入口直接运行Forge/npm make/Gradle充当正式发布。当前已接入配置，真实构建及包内版本/入口/签名仍待验证。

Electron 需 WiX v3、有效 OpenVPN payload；Android 需 JDK 17、SDK/Build Tools 35、项目 NDK 及依赖。脚本临时修改源码入口配置并在正常结束时恢复；禁止并发构建或删除活动锁。强制中断后先检查配置恢复情况。

WiX已支持从WIX/bin、WIX便携目录、PATH及默认v3.14/v3.11目录自动识别。本机已验证`D:\tool\wix311-binaries`中的candle/light版本为3.11.2，无需重复安装或修改系统环境。当前9项工具回归通过，MSI+Android只读预检查无阻塞，版本1.0.19/versionCode 1019；这不代表已生成安装包、签名验证或安装验收通过。证书信任兼容性及旧APK覆盖升级仍未验证。

新入口的私有CA必须先适配源码信任策略，不能认为修改`config/client.env`就会自动信任。服务端无固定IP的本地证书模式已获准接受浏览器告警，但不表示Electron/Android会放行证书主机不匹配，不能全局关闭客户端证书校验。Android默认入口为构建期配置。APK/MSI签名身份与有效性均须实测报告，不依据文件名或旧清单判定。MSI安装/升级/VPN/卸载须在隔离Windows测试机验收，不自动在开发机卸载旧版。

## 6. 验收与回滚

分层记录通过/失败/阻塞/未验证，不把启动成功当全部通过：

1. 构建及 SHA256、镜像 digest/架构；容器无重启循环。
2. 公网严格 TLS、业务页面、API UP、新资源摘要、内部接口 404。
3. 页面与 iframe 同 origin；WS 101 后仍须验证真实 XMPP/入会会话。
4. 品牌/CSS、插件实际加载；主持人 OWNER、普通成员 PARTICIPANT。
5. 三端或关闭 P2P 走 JVB，双向音视频、ICE/UDP、共享及重连。
6. MSI/APK 签名、安装升级与实际运行，VPN 按本次范围验证。

更新前保存旧配置、产物、镜像摘要及一致性数据备份。回滚仅恢复本实例批准范围，注意数据库兼容，不覆盖更新后用户数据；恢复后重新检查接口、数据及会议。证书和秘密不因代码回滚随意更换。

## 7. 历史目录清理门禁

旧部署目录尚未删除。清理前须迁入必要的最新安装包、manifest/验收证据和实例资料，修正工作区说明/技能对历史路径的引用，验证独立配置和脚本。不要把本目录已复制配置误认为整个迁移及删除工作已完成。
## 主持人转让（2026-11-12）

依据[统一规范](AGENTS.md)，所有新正常部署默认开启主持人转让，由正式build-tools组包及公共安装核心完整接入API内部鉴权、仅容器网络内部HTTPS和Prosody插件/撤权配置，不另走补丁包安装。秘密及CA私钥在目标生成；找回及管理员恢复仍默认关闭。

当前代码仍在集成，完整回归及CI受控输入同步未完成，未生成新包或修改47服务器。材料检查不代表运行验收。历史增量维护步骤见[转让说明](patches/prosody/HOST-TRANSFER.md)，不是新部署入口。

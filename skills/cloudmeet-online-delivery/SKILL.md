---
name: cloudmeet-online-delivery
description: Use when the user requests CloudMeet standard online delivery, Actions builds, Windows/Android clients, deployment or acceptance through Hermes, including short origin-only prompts.
---

# CloudMeet 标准线上交付

操作指南，不是第二份规范。先读取知识库 README、standards/project-delivery.md、audits/project-register.md 及配置库 AGENTS.md；核验实际 main/SHA/脏状态，记录本次加载版本。不可访问即阻断，不用会话记忆代替。

## 短提示词与固定选择

`按 CloudMeet 标准交付流程，将当前批准源码完整交付到 https://118.193.36.35:8443，执行到部署与验收。`

这是本次明确执行请求；先预检后在所请求范围连续执行，不重复确认固定选择、不要求长提示词或逐步确认。只说“预检/计划/打包”时严格止于该终点，不自动发布/部署。新凭据/材料缺失、目标歧义或超授权操作一次性报告具体阻塞；破坏性操作仍须范围明确的二次批准。

现行知识库明确完整执行请求包含标准链内专用Runner/变量/正式台账首次初始化及独立恢复核验、已有批准签名材料的受控Secrets配置；不额外索取B1/B2/B3/B4/B5确认。基础设施不具备时先按标准整改，不因只是缺安装就重复问方案；实际缺账户权限、真实身份/材料或安全隔离能力才报告具体阻塞。此流程修复任务本身不等于已经发起新的完整交付任务。

| 用户仅提供 | 执行者负责，不再询问 |
|---|---|
| 完整 origin（协议/主机/端口）及任务终点 | 自动修订 rN、同机媒体IPv4、端口、签名、首装入口、main闭环 |

已有完整 origin 就使用，不要求重新输入。缺 origin 时只问这个值。2026-11-20用户二次确认：Windows EXE/MSI取消代码签名，交付明确unsigned，不要求Windows PFX/SignTool或代码签名验签；Android保持现有keystore和批准DER核验，两端HTTPS CA限定信任不变。首次安装固定 setup.py，不把 online_update 当首装选项；发现既有实例停止首装、报告事实，不覆盖既有数据。

## 实际入口

2026-11-23增量契约：原流程保留，统一交付范围加入H5，成为七服务＋H5＋双客户端。H5锁定于config/h5-source.json，继承原父Run修订号；检查H5_SOURCE_READ_TOKEN最小跨库读权限。首装/升级及离线附加均包含H5，不另开独立批次；双客户端交付位置不变。新公共核心仅额外允许严格H5路由/只读挂载差异，不放开其他配置/schema迁移；旧instance显式证书差异无法匹配时阻断，不覆盖成tls internal。缺H5或真实验证证据不得称完整交付。

- 配置库 stevenzxs/cloudemeet-deploy（历史拼写），持久副本 `/opt/data/workspace/delivery/cloudemeet-deploy`；Git 使用 `core.sshCommand=ssh -F /opt/data/delivery-controller/ssh/config`。知识库在 `/opt/data/workspace/knowledgebase`。只对干净副本快进同步，不 reset 并发工作。
- gh `/opt/data/delivery-controller/gh`，`GH_CONFIG_DIR=/opt/data/delivery-controller/auth`；不显示认证内容。不用知识库专用凭据执行交付操作。
- 118既有严格SSH入口 `ssh -F /opt/data/.ssh/config cloudmeet-118`；先只读核对主机身份/架构/容器/卷/目录/端口/资源。历史状态和不可用别名不代替当前事实。其他 origin 必须核验实际目标身份，不能默认为118。
- 证书/签名工具和公开身份唯一维护源 stevenzxs/cloudmeet-certificates，固定提交见 `config/signing-policy.json`。不从聊天临时生成签名器/安装器。

## 一套标准执行顺序

1. **预检和固定身份**：查询现有GHCR镜像、Run、源码锁定SHA和配置main；明确本次是否要求完整新构建。检查Android两项Secrets、批准DER指纹；Windows不要求代码签名材料/SignTool或私有证书库检出，不安装签名根。检查两端公开HTTPS CA；只看Secrets名称，不读取值。缺材料列准确名称及安全提供位置。
2. **版本基础设施**：专用150控制Runner、持久仓库外SQLite、`CLOUDMEET_VERSION_LEDGER`、独立备份恢复与最新计数证据一起核验。采用标准规范方案，标签不等于Runner隔离；实测账户支持的Runner组/工作流限制及可信执行边界，无法满足则阻断，不降低隔离。已授权基础设施实施时直接执行该标准方案；未授权写操作时一次报告具体边界。正式台账丢失不自动重建，恢复须核对独立Run/高水位证据；禁止把纯预检当正式占号或承诺r1。
3. **统一参数**：运行 `python3 -B build-tools/delivery-target.py --origin <origin>` 预览；IPv4直接复用MEDIA_HOST，域名用当前解析及独立核验的同机IPv4，经 `--verified-target-ipv4` 输入工具，歧义阻断。MEDIA_PORT来自受控target.env，不从网页端口猜。将工具输出的入口三项更新到唯一config/client.env，CLIENT_VERSION保持批准基线。包外实例配置通过 `--target-env <仓库外绝对路径>` 创建，不修改包内文件。修改/测试后提交推送并合入main，再固定最终完整SHA；只推任务分支不算完成。
4. **联合构建/发布**：审阅当前 `build-joint.yml`、复用工作流的触发器/权限/Secrets/目标；显式 material_commit=本次最终配置SHA、118 architecture=amd64、在本次授权发布范围内 publish_images=true。不要用旧actions.py的手填--version示例调度新入口。新顶层Run在产品测试/构建前分配N，失败取消占号、同Run重跑复用、子流程继承；不另开客户端Run重复占号。不在150/目标机/Windows编译服务端，不自动离线回退。
5. **跟踪与制品**：调度前落盘意图和任务ID，查询关联Run，记录head_sha/Run ID/attempt；HTTP204不等于成功。有限等待，网络超时先查状态，不重新dispatch。核验完成结论、实际矩阵、artifact来源/外层摘要、内层SHA256SUMS、七镜像固定digest和config身份。双客户端最终APK/MSI/PE版本、ABI、origin、CA必须通过；Android比对批准签名身份，Windows记录unsigned及未知发布者/SmartScreen风险，不写验签通过。其余门禁失败仍阻断。
6. **发布后选择与目标执行**：七服务与双客户端全部成功才联合发布；七镜像GHCR固定digest及客户端/公开材料GitHub Release持久保存，draft全部资产上传后公开，部分失败不称完整发布。运行`delivery-route.py --origin <已构建origin>`，只补问缺失的首次/升级、服务器地址、入口；已有值复用。入口/公开CA必须匹配构建结果，不能发布后改值冒充客户端已适配。首装用本批setup.py/摘要、无镜像online归档/摘要、registry/独立可信摘要、独立安全传输的cert.tar.gz及包外target.env：`setup.py --server-package <包> --verify-origin <origin> --target-env <外部绝对路径> --registry <registry.json> --registry-sha256 <可信摘要>`，按digest拉取，不编译。已有实例只能走升级，不用首装覆盖。升级从新材料运行`online_update.py`，必填`--root`/`--project`/`--target-env`/`--verify-origin`/`--ca`/`--candidate`/`--registry`/`--registry-sha256`，默认只读；已授权更新时加`--apply`。严格绑定七容器归属，核对配置/补丁兼容、TLS/API及空闲后备份；当前仅image-only，不自动配置/schema迁移。保留数据/秘密/CA/证书，失败旧image ID恢复服务，不恢复数据库覆盖新数据。新CA轮换仍另批，失败保留目录和阶段，不清理重装。
7. **验收与闭环**：分别报告构建、签名、发布、制品核验、安装、HTTPS/鉴权/信令、客户端安装和媒体结果。JVB媒体用三客户端或禁P2P，并记录实际JVB链路；两客户端P2P不能证明JVB可用。材料/设备不足列待核验，不虚报完成。知识库唯一台账按短分支→提交推送→合main→核验→删已合分支闭环，保全并发变更。

## 断点与停止

离线是显式附加节点而非pull失败回退：使用同库cloudmeet-deploy-offline Skill及offline-export.py，从已发布固定digest导出，不新占rN/重新编译。目标首装/升级共用公共安装核心，离线升级显式--offline-package，只load不pull。需要已有匹配Linux Docker Engine；包内Compose不等于完整引擎首装闭包。脚本/Skill到位不代表上述真实发布或安装已验收。

仓库外受限检查点记录任务终点/授权范围、origin与派生值、三库SHA、Run/attempt、N、制品ID/摘要/digest、当前阶段与下一步。恢复先比较真实Run和目标，不重复占号、构建或首装。新秘密通过受限渠道提供，不在聊天粘贴；CA私钥不进Actions/镜像/目标包。

同步安装仅证明文件到位；静态契约回归不证明模型已加载或整链验收。Android签名及基础设施是否可用以本次实测为准，不把本文存在当就绪。

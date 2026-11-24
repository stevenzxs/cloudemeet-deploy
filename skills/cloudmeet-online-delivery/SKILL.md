---
name: cloudmeet-online-delivery
description: Use when the user requests CloudMeet standard online delivery, Actions builds, Windows/Android clients, deployment or acceptance through Hermes, including short origin-only prompts.
---

# CloudMeet 标准线上交付

操作指南，不是第二份规范。先安全同步知识库与配置库最新已批准的 origin/main 至本地副本，再读取知识库 README、standards/project-delivery.md、audits/project-register.md 及配置库 AGENTS.md 和执行材料。同步前检查并按现有要求备份，只安全快进，不覆盖或丢弃本地工作；无法安全同步或读取时，报告具体阻塞并停止。

## 短提示词与固定选择

`按 CloudMeet 标准交付流程，将当前批准源码完整交付到 https://118.193.36.35:8443，执行到部署与验收。`

这是本次明确执行请求；先预检后在所请求范围连续执行，不重复确认固定选择、不要求长提示词或逐步确认。只说“预检/计划/打包”时严格止于该终点，不自动发布/部署。新凭据/材料缺失、目标歧义或超授权操作一次性报告具体阻塞；破坏性操作仍须范围明确的二次批准。

现行知识库的后续批准采用GitHub托管Runner与专用Git台账；完整执行请求包含标准链内变量配置、既有历史迁移及独立恢复核验、已有批准签名材料的受控Secrets配置；不额外索取B1/B2/B3/B4/B5确认。不恢复旧150 Runner或重建SQLite计数。实际缺账户权限、真实身份/材料或可信执行能力才报告具体阻塞。此流程修复任务本身不等于已经发起新的完整交付任务。

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

### 对话进度操作约定（2026-11-24已批准，自动化接通待验）

先给本任务固定编号步骤表、目标/终点；按任务范围生成，不给既有发布部署增加构建/占号。每步开始和状态变化向原对话报告`[04/08][执行中] 镜像拉取｜本步01:20｜累计03:15｜已验证4/7`，长步骤约60秒补充有据进展。失败报告现网影响/恢复位置，不重置重试历史，不伪造百分比/ETA；不支持推送须说明，终端日志不是消息送达。恢复/回滚结果不能写成升级成功。

自动化实施计划见`docs/plans/2026-11-24-delivery-reliability-progress.md`。目前公共入口尚无贯穿全链的编号/计时事件和Hermes真实对话投递适配，不得仅因本节存在宣称已实现；未具备时按可核验事实人工报告，未知历史耗时标未知。后续自动化须从同一持久任务事件呈现，保留事件游标/待投递项，真实通道验证后才能声称自动通知可用。

1. **准备并启动新构建**：同步两库并读取执行材料，使用提示词中的目标入口；源码与构建配置以仓库维护内容为准，不另行分析、挑选或确认版本。只检查本次所需权限、Android签名及公开HTTPS CA材料是否可用，不在此完成全部验收。不查询历史镜像或历史Run，不判断复用，只有启动一次新构建这一个选项。遇到具体阻塞，报告失败动作、错误和停止位置，不作进一步分析。本步骤结束时，输出本步骤成功/失败状态及实际耗时，耗时单位为分钟，作为流程埋点，供后续优化流程使用。
2. **自动版本分配**：由本次联合构建的版本分配器自动分配修订号，使用仓库维护的版本配置。Hermes读取分配结果，不重复检查台账、锚点和迁移历史。分配失败时，报告具体错误和停止位置，不作进一步分析。本步骤结束时，输出本步骤成功/失败状态及实际耗时，耗时单位为分钟，作为流程埋点，供后续优化流程使用。
3. **应用入口参数**：使用提示词中的目标入口，由工具生成客户端及部署参数，其余参数使用仓库配置，不重复询问或逐项分析。将工具生成的参数及本步骤使用的仓库配置参数输出告知用户，只做陈述，不作分析；参数输出限公开配置，不输出密码、令牌或私钥。需要修改配置时完成提交并合入main；无变化不提交。失败时，报告具体错误和停止位置，不作进一步分析。本步骤结束时，输出本步骤成功/失败状态及实际耗时，耗时单位为分钟，作为流程埋点，供后续优化流程使用。
4. **联合构建/发布**：审阅当前 `build-joint.yml`、复用工作流的触发器/权限/Secrets/目标；显式 material_commit=本次最终配置SHA、118 architecture=amd64、在本次授权发布范围内 publish_images=true。不要用旧actions.py的手填--version示例调度新入口。新顶层Run在产品测试/构建前分配N，失败取消占号、同Run重跑复用、子流程继承；不另开客户端Run重复占号。不在150/目标机/Windows编译服务端，不自动离线回退。
5. **跟踪与制品**：调度前落盘意图和任务ID，查询关联Run，记录head_sha/Run ID/attempt；HTTP204不等于成功。有限等待，网络超时先查状态，不重新dispatch。核验完成结论、实际矩阵、artifact来源/外层摘要、内层SHA256SUMS、七镜像固定digest和config身份。双客户端最终APK/MSI/PE版本、ABI、origin、CA必须通过；Android比对批准签名身份，Windows记录unsigned及未知发布者/SmartScreen风险，不写验签通过。其余门禁失败仍阻断。
6. **发布后选择与目标执行**：七服务与双客户端全部成功才联合发布；七镜像GHCR固定digest及客户端/公开材料GitHub Release持久保存，draft全部资产上传后公开，部分失败不称完整发布。运行`delivery-route.py --origin <已构建origin>`，只补问缺失的首次/升级、服务器地址、入口；已有值复用。入口/公开CA必须匹配构建结果，不能发布后改值冒充客户端已适配。首装用本批setup.py/摘要、无镜像online归档/摘要、registry/独立可信摘要、独立安全传输的cert.tar.gz及包外target.env：`setup.py --server-package <包> --verify-origin <origin> --target-env <外部绝对路径> --registry <registry.json> --registry-sha256 <可信摘要>`，按digest拉取，不编译。已有实例只能走升级，不用首装覆盖。升级从新材料运行`online_update.py`，必填`--root`/`--project`/`--target-env`/`--verify-origin`/`--ca`/`--candidate`/`--registry`/`--registry-sha256`，默认只读；已授权更新时加`--apply`。严格绑定七容器归属，核对配置/补丁兼容、TLS/API及空闲后备份；当前仅image-only，不自动配置/schema迁移。保留数据/秘密/CA/证书，失败旧image ID恢复服务，不恢复数据库覆盖新数据。新CA轮换仍另批，失败保留目录和阶段，不清理重装。
7. **验收与闭环**：分别报告构建、签名、发布、制品核验、安装、HTTPS/鉴权/信令、客户端安装和媒体结果。JVB媒体用三客户端或禁P2P，并记录实际JVB链路；两客户端P2P不能证明JVB可用。材料/设备不足列待核验，不虚报完成。知识库唯一台账按短分支→提交推送→合main→核验→删已合分支闭环，保全并发变更。

## 断点与停止

离线是显式附加节点而非pull失败回退：使用同库cloudmeet-deploy-offline Skill及offline-export.py，从已发布固定digest导出，不新占rN/重新编译。目标首装/升级共用公共安装核心，离线升级显式--offline-package，只load不pull。需要已有匹配Linux Docker Engine；包内Compose不等于完整引擎首装闭包。脚本/Skill到位不代表上述真实发布或安装已验收。

仓库外受限检查点记录任务终点/授权范围、origin与派生值、三库SHA、Run/attempt、N、制品ID/摘要/digest、当前阶段与下一步。恢复先比较真实Run和目标，不重复占号、构建或首装。新秘密通过受限渠道提供，不在聊天粘贴；CA私钥不进Actions/镜像/目标包。

同步安装仅证明文件到位；静态契约回归不证明模型已加载或整链验收。Android签名及基础设施是否可用以本次实测为准，不把本文存在当就绪。

## 已核实的常见坑（2026-11-24）

- 仓库规范名是 `stevenzxs/cloudemeet-deploy`。旧拼写 `cloudmeet-deploy` 只剩重定向：`gh api`/`gh run list` 用旧名会 404，git 传输仍可能成功，不能据此判断仓库不存在或另建仓库。
- H5 源 `stevenzxs/jitsi-weixin` 当前为 public：按 `config/h5-source.json` 固定提交匿名检出即可。`H5_SOURCE_READ_TOKEN` 值失效时，强制携带会让 `actions/checkout` 发送无效认证头并报 `could not read Username`；该 secret 已改为 optional，不要再无条件传入。
- 无人值守 cron 会话禁止 sudo 与危险命令：升级 apply 必须在 118 以 root 写实例目录、备份并执行 compose，只能在交互会话或显式开启 `approvals.cron_mode` 的会话中执行；cron 内只做只读目标核验，并如实报告该阻塞。
- 治理回归与布局检查要求目录名为 `deploy`：在 `/opt/data/workspace/delivery/` 建 `deploy -> cloudemeet-deploy` 软链即可原样运行，不需要改仓库或测试。
- 150 到 GitHub 的 Release 资产下载经常被限速到几十 KB/s：先核对 `SHA256SUMS` 已下载部分，大资产用 `curl -C -` 断点续传并明确标注“未完成”，不要以 job 成功代替已交付。

## 2026-11-16 本地WSL构建批次 11248.0.1 交付并部署至 118

- 用户批准路线变更：不用 Actions runner，本机 WSL 从锁定源码完整编译七服务（amd64），版本 11248.0.1，批次 11248.0.1-local-1（本地 run 标记），部署材料提交 772787c。
- 已发布 GHCR：ghcr.io/stevenzxs/cloudmeet-<service>:11248.0.1-amd64，7 digest 与构建记录逐一相等（见 release/amd64/server/11248.0.1-local-1/ghcr-digests.txt）。
- 组包 PASS_PACKAGE_INTEGRITY_ONLY（45 文件，864,709,048 字节，SHA256 cfaec3a69684a7453a8f246b5b33a7993e26b566af5de48cee056fc92a833b60），交付 deploy/release/amd64/server/11248.0.1-local-1/。
- 容器化存储语义偏差（构建机与 118 均为 containerd store，inspect Id=manifest list digest）：记录 image_id 用 index digest 并新增 image_config_id；仅构建侧克隆对 install.verify_image_archive 做最小增量（接受 image_config_id），目标机包内代码零修改。inputs.sha256 已同步两次本地材料增量（target.env 的 MEDIA_HOST=118.193.36.35；install.py 增量）。
- 118 全部 frp（frps/frpc/配置/证书/单元）已按用户指令清退；gateway 直绑 0.0.0.0:8443，JVB UDP 10000（advertise 118.193.36.35，NAT 后端 10.7.163.131）；新增 2G swap。
- 部署：拉取路线（GHCR pull→retag→包内 initialize/start 原链）至 /opt/cloudmeet/11248.0.1，compose project cloudmeet-1124801-local-1，7 容器全 Up。
- 验收：公网 https://118.193.36.35:8443 下 /cm/desktop 200、/cm/ 200、/mapi/actuator/health UP、会议页 200、/http-bind 200；JWT 秘密为首次生成。媒体（UDP10000 经 NAT）与客户端信任（Caddy tls internal 私有 CA）未验收，不宣称可用。
- 旧 /opt/cloudmeet-jks 数据保留未动；未改 202 生产与其他实例。
# 当前执行记录

## 2026-11-20 客户端去重预检与阶段提示

- 用户在评估后批准优化、提交推送并启动Actions：工作流每目标只运行一次正式命令，内部版本/配置/CA/工具/签名前提预检及阻塞退出保留，--check仍支持独立诊断。阶段提示写stderr，保留--check stdout JSON兼容；外层提示改为build or package verification failed，避免误指所有失败均为验包。
- 未改35分钟超时、签名身份或最终验包门禁；不宣称能解决既有Electron等待或Android资源检查失败。新增回归先失败后实现；全量客户端测试及摘要结果、配置SHA/150同步/新Run证据见唯一台账。用户批准新联合Run沿用amd64七服务及双客户端、118:8443、发布镜像不部署；未取消原Run，不重复调度。

## 2026-11-20 JVB依赖请求502诊断与有限同源重试

- Run44712420525 r10的JVB主模块解析直接test依赖jersey-test-framework-provider-grizzly2:3.1.11的POM失败；前三模块成功，路由审计1299条中1286个200、12个404、1个502。旧日志未区分上游HTTP502与代理转换的网络异常，实际底层原因不可追溯。两源当前POM内容一致且校验匹配，不据此冒称Runner历史网络正常。
- 已提醒正常流程失败策略变更，用户“执行修复”确认同源最多3次、2/5秒退避及诊断方案；不启动新Actions或部署。新增回归先失败后实现，16项定向测试通过：502/503/504、超时/重置重试；耗尽停止、404回退后Central重试；TLS/鉴权/429拒绝、凭据不回显与真实回环HTTP字节传输。JVB源码及锁定版本、签名/摘要门禁保持不变。云端产品验证待另行授权新Run。

## 2026-11-20 无冲突重复客户端配置

- 用户先确认Android有限放宽，随后确认Electron相同值重复键范围，并要求提交、150同步后新建联合Actions；沿用amd64七服务及双客户端、https://118.193.36.35:8443、发布镜像但不部署。未延长35分钟超时、不更改签名身份或产品源码。
- Android仅允许直接顶层、显式禁止明文、限定同一主机及预期CA、完整结构一致的重复规则，输出警告；零匹配、冲突、继承或扩大范围拒绝。Electron相同值重复键警告，冲突仍拒绝；最终MSI检查保存警告。新增回归先失败后实现，40项客户端辅助测试通过；最终验证/同步/调度证据见唯一台账。
- 原Run44702260669 attempt2最终failure：Android Gradle BUILD SUCCESSFUL in 23m22s，最终资源规则数量断言失败，实际匹配数及APK解码XML未取得；Electron35分钟步骤超时，日志停在主程序签名工具报告成功，未完成最终签名/包验收；API Central429，组包/发布跳过。有限放宽不等于这些根因全部修好。

## 2026-11-19 Electron旧Actions失败诊断

- 对照用户粘贴日志，API核验Run44023749308 attempt1、配置e256f5de39956b96e344f5a98ccccdd488080962；npm ci、WiX检查通过，Forge子进程失败（不等同最终包校验失败），artifact总数0。当前远端main为a973e0e，旧日志的可未签名提示不是当前流程执行结果。
- 已确认诊断缺陷：run()只记录临时日志路径，不报告子进程退出码，也不向always审计目录保留详细错误。修复退出/信号/spawn错误及有限脱敏尾日志、脱敏审计日志留存；不上传候选/原始日志、命令参数或环境，不放宽签名/版本门禁。
- 三项新增回归先失败后通过（真实fixture子进程exit7、ENOENT及凭据/私钥脱敏）；完整客户端36/36通过。旧Runner详细日志无可取回制品，具体Forge编译根因仍待核验，不能宣称产品构建已修好。未分配正式版本、调度/重跑Actions、编译产品、签名、发布或操作服务器。

## 2026-11-19 标准短入口及强制签名流程修复

- 用户批准固定标准选择，不再反复确认：完整origin及终点、rN、媒体派生、Windows必须签名、首装setup.py、修改合main。知识库及本AGENTS记录范围，新增线上Skill唯一版本维护源，150安装须备份后核摘要。
- delivery-target.py复用target.py校验器，IPv4复用媒体主机、域名须当前唯一A及独立同机证据；仅生成包外实例配置，不调度/占号/部署。config/client.env仅入口改118，基线不变。
- Windows工作流强制身份/Secrets/私有证书库只读凭据；证书库固定工具先签主程序、再统一MSI并签最终包，最终签名/批准DER/时间戳核验。APK强制唯一批准DER指纹；无未签名降级。
- 初始拒绝测试确认旧实现缺签名校验函数/统一目标工具/受管线上Skill；后续客户端33项、标准流程4项回归和actionlint通过。Linux无Docker辅助98/99、治理2/3，均仅原有受保护output/assemble-11248.0.1.sh未登记失败保持，不删改/屏蔽历史文件。
- 未执行正式分配、Runner安装、台账初始化、产品构建/签名/发布或118部署。真实Windows身份仍缺，未来必须先登记批准公开身份并更新工具SHA；Runner隔离/正式台账恢复、最终JS/Hermes bundle、首装失败保留状态恢复、真实最终包/升级/客户端/JVB媒体仍待核验，不关闭GOV/AUD门禁。静态/行为模拟不当作Hermes活会话加载或整链通过。

## 2026-11-19 用户批准启用版本配置（控制端未就绪）

- 用户最终确认服务端11248.0.1，撤回此前11248.0.2选择；客户端1.0.21。现存正式交付APK/MSI实际元数据及SHA256已只读核验，用户批准以Android1021/MSI1.0.21为升级兼容基线，不明更早时间计数测试包不在保证范围。
- config/version-policy.json批准开关置true，纯r1预览为11248.0.1+r1 / 1.0.21+r1 / Android10211 / MSI1.0.22 / PE1.0.22.0；详见VERSION-ACTIVATION.md。以下较早“未启用”段落为历史阶段证据。
- 仅配置启用，不安装Runner、初始化正式台账、正式占号、触发Actions或构建/签名/发布/服务器操作。控制端与备份恢复、真实包/签名/升级仍待核验，不关闭GOV/AUD既有缺口。

## 2026-11-19 联合版本改造（未启用）

- 新增统一版本派生、仓库外SQLite事务分配、父Run继承核验及attempt追加证据；独立入口和联合7+2入口去除手填版本/旧默认回退。失败占号、重试复用，子工作流不新建分配。
- Android为1021拼接N；显示1.0.21+rN，MSI=1.0.(21+N)，PE增加第四段0。服务端使用批准基线+rN及安全tag，保留组件源码/上游身份。最终包和来源清单带分配记录；历史材料不修改。
- config/version-policy.json保持approved=false；服务端基线、历史Android/MSI最高版本及专用150控制Runner未核验/未安装。未建立正式台账、未正式占号、未运行Actions/构建/签名/发布或操作服务器。整库回滚检测依赖恢复前独立证据核验，不声称SQLite能自动阻止旧快照恢复。
- 当前验证与剩余问题见REVISION-PLAN.md及知识库唯一台账，未关闭GOV-03/04/05及AUD-015~017。

## 2026-11-19 第二轮复审修复（本地，未发布）

- start.runtime_environment统一公共/目标/秘密来源，宿主仅保留工具与Docker连接环境，不继承COMPOSE_*或任意插值；前检使用同一解析器及假秘密，实际启动及换证Compose使用显式env。
- 本次有效target摘要传递给initialize/start，变化拒绝；换证前再次核对。直连origin端口必须匹配HTTPS_PORT，gateway/JVB发布绑定限制为通配，未隐式增加反代/端口转发模式。
- Android从aapt资源表恢复逻辑引用，apkanalyzer解析实际成员路径；CA摘要仅检查raw资源映射出的成员。历史APK只读实际工具检查已验证Manifest→受管入口，不代表其CA/签名/bundle/安装验收。
- 尚未完成：授权签名指纹输入、失败分阶段恢复、最终JS/Hermes bundle验证及Hermes完整编排。未改历史包或删除数据；本轮未编译产品/调度/签名/发布/服务器操作。

## 2026-11-19 审计后主线收敛（本地实现，未发布）

- 保留package/build/publish及首装/更新现有入口，不新增打包线。setup/deploy新增显式包外target-env；target.py统一解析，初始化与启动继承。目标参数和Compose审计前移到镜像导入/秘密生成前，包外报告不破坏原摘要。
- gateway两项TCP及JVB UDP精确映射必需，拒绝缺失/错端口/错协议；新增回归复现原误放行及首装迟拒绝。
- 客户端前检/源码清单复制到候选并随交付；Android检查Manifest/受管入口/主机CA引用，移除原始AXML字串回退。真实工具若不能保留domain文本将明确阻塞；最终JS/Hermes bundle默认入口仍未验证。
- Hermes任务Run关联/等待/下载摘要验证、150证书库签名交接及首装/更新自动分流尚未实施，不声称整链收敛完成。签名实际路径未确认，不上传Secrets、不猜命令。
- 本轮仅无Docker辅助回归；未编译产品、触发Actions、签名、发布或操作服务器。历史output布局文件保留，最终验证结果见知识库台账。

## 客户端完整交付流程修复

- 用户确认正常打包必须走到release交付，不以设备安装/媒体作为门槛。build入口改为最终包检查后调用delivery，输出实际路径与摘要。
- 新增verify-package.cjs与delivery.cjs，最终MSI管理解包检查配置/PE/版本/签名状态，APK读取最终资源/版本/ABI/签名及CA，失败明确阻塞；未签名MSI如实记录。历史包及其证据不修改。
- 17项工具回归及JS语法/差异检查通过。新增最终包检查适配器尚未在真实MSI/APK端到端执行，不声明本批历史未验项已关闭；本轮未重编、安装设备、提交推送。

## 客户端平台/架构目录

- 用户批准clients按windows或android，再按实际架构/ABI和批次分类；排除32位x86，Windows目前仍仅构建x64。
- 候选收集记录平台、实际ABI与交付目录模板；Android临时移除x86过滤并在结束恢复源文件，APK通过Python标准库读取真实lib ABI，多ABI使用universal且记录集合。不移动历史产物，不触发编译或自动晋级。
- 修正既有预检查测试硬编码1019，改为按当前配置版本派生，保留用户client.env不动。

## setup解压执行权限修复

- rc6目标首装在Compose检查前失败：setup按.sh后缀赋执行位，错误将bin/docker-compose解压为0644。改为依据归档任意执行位映射0755，否则0644，不继承setuid/setgid/sticky或写权限。
- 回归加入无扩展名且原始mode=06755的Compose模拟文件，修复前失败(0644)，修复后要求0755。历史rc6包不修改，服务器不自动操作；既有解压目录按定点chmod后直接deploy继续，不重跑setup。

## 目标侧证书组合实现

- 用户随后明确批准完整流程提交、推送与启动Actions；本批1.0.19-rc6原生amd64完整重编七服务，材料提交锁定。Actions不接触cert.tar.gz；成功下载材料校验后，本地交付目录旁置私有证书包、独立/总摘要与说明，不修改server归档字节，不执行服务器安装。

- 用户批准：固定cert.tar.gz仅目标侧旁置，不进入Git/Actions/server归档；新增setup.py及独立摘要随公共artifact输出。
- 公共certificate.py限定安全成员及包内摘要、预检SAN/链/期限/密钥；setup暂存证书，deploy必填verify-origin，首启后换外部证书、仅重启gateway并严格验证/cm/desktop/。
- 不执行证书包内脚本，不改内部TLS；首次失败保留数据。仅无Docker辅助回归，尚未目标安装或运行验证；本轮未授权提交/调度或服务器变更。

## cert issue归档输出

- 用户同意保留issue目录并自动输出同名tar.gz及sha256；init-ca不归档，不改历史包、不连接服务器。
- 使用Python标准库tarfile，限定包内摘要清单成员，拒绝ca.key/符号链接/额外文件及已有归档；归档脚本0755、私钥0600、根目录0700，生成后复读核对内容。

## 2026-11-13 首启TLS清单与镜像校验补全

- rc4已导入七镜像并生成秘密，首启因OpenSSL未保留ca.srl被误拒绝；start.py现在允许该序列号辅助文件缺省，仍要求六项TLS材料、权限、证书链/主机及公私钥匹配，拒绝额外文件及业务数据。
- start.py镜像检查复用deploy.py归档绑定身份逻辑，消除上一修复遗漏的第二处config-ID假设；不放宽架构或身份链。
- 用户要求继续修复；延续提交推送/Actions范围，新amd64版本1.0.19-rc5完整七服务；不原地修改rc4历史包、不清除115的.env/data、不执行远端恢复。rc4恢复需另交付经校验维护材料与明确操作，不可重跑first-install或直接覆盖新包。

## 2026-11-13 Docker 29/containerd安装身份修复

- 115只读排查证实：Docker 29.7.2/containerd镜像存储的inspect.Id为OCI manifest摘要77be4963…，归档manifest引用批准config bc64fc9b…；包摘要、平台、Config与RootFS一致，旧安装器误将manifest摘要与config摘要比较。
- 公共deploy.py保留传统config-ID检查，同时允许经过归档index成员、manifest内容SHA256及其config引用验证的manifest-ID；前置已有标签与导入后均调用同一校验。错误ID、错误config、错误架构仍拒绝。
- 用户授权修代码、提交推送与启动新amd64 Actions；完整重编七服务，不修改历史包、不在服务器安装。新版本1.0.19-rc4，无固定网页IP及既有引擎前提保持不变；运行/媒体兼容性仍未验。

## 2026-11-13 amd64打包适配

- 首次run43360382722失败：基础镜像校验内Python使用单引号环境变量键，被外层Shell单引号吞掉而NameError；七服务尚未编译，组包跳过。修正双引号并新增真实Shell管道回归；新run完整重编，不复用失败批次产物。

- 用户批准统一入口支持原生amd64，提交推送并触发Actions，终点为下载材料校验后的完整包；不操作服务器、不发布镜像。
- workflow按architecture选择原生runner，脚本统一派生镜像平台、Java/Go、Compose和包/安装器架构。
- 核对Jitsi stable-11248索引03a73ca2…包含原ARM子manifest48f5eb97…及amd64子manifest88283823…；Debian/nginx固定索引均有amd64，不复用ARM应用镜像。
- 当前仅无Docker辅助回归；真实构建run及下载结果待后续记录，未声明安装或媒体通过。

## 2026-11-12 首次安装TLS目录与启动保护冲突修复

- initialize生成data/host-control后，旧start拒绝任何data目录，正常首次安装因此自相矛盾。新增真实OpenSSL生成→首次启动前置检查回归，修复前复现拒绝。
- start仅允许初始化精确文件集合；检查符号链接、私密文件权限、证书链/时效/网关身份及证书私钥匹配，不重建秘密/证书。业务数据、额外项或不完整材料仍拒绝。
- WSL无Docker回归49项通过；未执行目标续跑、容器启动或会议验收。历史归档不修改，源码修复未提交推送。

## 2026-11-12 修复内部鉴权变量导致的组包渲染失败

- run43195935735在Compose静态渲染阶段缺少JITSI_ROLE_CHECK_SECRET而退出，未完成组包。
- package.sh仅在渲染命令环境中补RENDER_ONLY占位值，不写入交付配置；目标安装随机密钥机制不变。
- 回归清除继承环境变量并检查渲染进程收到占位值，修复前空/显式媒体地址两种场景均复现失败。无Docker辅助回归，不代表目标运行验收。

## 2026-11-12 build-tools纳入部署仓库

- 用户已移动目录到deploy/build-tools；修正客户端工作区定位、测试/config路径、布局登记及文档，开放Git跟踪build-tools和.github。正式workflow放入部署仓库，模板与实际文件保持一致；不再人工同步CI副本。
- 无Docker辅助回归：WSL服务器脚本48项、治理3项通过；Windows客户端CLI/core 11项通过。未运行服务器构建/安装，未提交推送，未同步技能安装副本。
- 主持人转让完整集成仍有此前记录的待验项；路径回归不代表运行验收或可发布。

## 2026-11-12 主持人转让默认能力文档同步

- 用户确认所有新正常部署默认开启主持人转让；找回及管理员恢复仍关闭。统一规范、部署README、build-tools说明、两个部署技能维护源与转让说明同步。
- 主流程为package.sh及offline-runtime；历史overlay不是新部署入口，不修改历史交付/验收记录。秘密及内部CA私钥目标生成，内部HTTPS不发布宿主端口。
- 代码集成、完整回归及CI输入摘要同步未完成，未提交推送/调度Actions/操作服务器。技能安装副本尚未同步，不等同维护源已部署到工具环境。

## 2026-11-12 修复Actions组包渲染环境被空值覆盖

- run 43155412543 attempt 1七服务镜像artifact上传完成，但组包Compose解析因SITE_HOST空值失败，未产生完整交付包。
- 根因：组包Shell仍从仅含注释的server.env.example读取SITE_HOST/JVB_ADVERTISE_IPS，覆盖target.py已导出的参数。移除两项旧读取，沿用校验后的目标环境；不更改镜像、鉴权或TLS模式。
- 新回归执行真实渲染Shell片段，以探针替代Compose二进制检查收到的环境及命令，覆盖空媒体地址和显式媒体覆盖。修复前两例均复现SITE_HOST为空；修复后无Docker回归48/48及Bash语法检查通过。
- 此回归不运行真实Compose/daemon，不代表Actions组包已成功。本次仅本地修复并同步受控CI副本，未提交、推送、重跑Actions或操作服务器。

## 当前：用户批准无固定网页IP与证书告警模式

- target.env仅保留协议、端口及可选MEDIA_HOST；移除SERVER_HOST。cloudmeet.internal仅为本地证书和上游兼容占位，不是客户端入口。
- Caddy default/fallback SNI配合catch-all路由，HTTP返回426；模板start及公共安装start通过同一target.py生成custom-config.js覆盖BOSH/WebSocket为浏览器同源，无需修改Web镜像。不同的既有custom-config.js拒绝覆盖。已核对锁定lifecycle启动脚本在system/settings之后追加custom-config.js。
- 新组包Compose端口与JVB_PORT保留运行时变量，不固化组包目标端口；manifest.origin为上游兼容占位，entry_mode声明请求入口自适应，不是真实访问地址。
- 不关闭客户端全局TLS校验，证书告警/兼容性风险明确接受；媒体NAT独立，未验证。不改服务器，不提交推送或触发Actions。
- 辅助回归47/47通过；Caddy 2.10.2 adapt --validate通过（仅配置解析/校验，不证明实际TLS握手、外网转发或浏览器可用）。未构建新镜像/交付新包。

## 2026-11-12 统一目标配置与config迁移收尾

- 本轮仅本地代码改造及无Docker检查，不提交/推送/调度Actions，不连接服务器，不改历史包。
- config/target.env为单机IPv4 HTTPS唯一地址/端口源；target.py严格校验并派生公共地址。jitsi.env独立维护公共参数；模板init及新包initialize仅动态生成三项秘密，不覆盖既有.env。
- config/start.sh固定deploy为Compose项目根，拒绝旧.env混入地址参数；旧实例需显式迁移，工具不自动改秘密或数据。
- workflow不再接受origin覆盖；组包携带target.env、同一加载器和jitsi.env，最终包文件仍采用既有包根布局。旧包运行时保留兼容分支。
- 本次没有实际原生构建或新包交付；最终辅助检查结果另以执行输出为证据。

## 2026-11-11 Actions打包脚本收敛

- 用户已要求“按建议优化打包脚本”；本轮终点为脚本修改及无Docker辅助回归，不自动提交/推送/调度Actions。
- 已确认：七服务每发布批次完整源码编译、统一版本及run/attempt，不用旧应用镜像补缺；后续发布仅使用已验包内镜像，不重编。
- 保留origin `https://47.110.84.166:8443`、HTTP重定向8080、媒体UDP10000及JWT/品牌补丁。目标由用户手动安装，当前宿主前提未知。
- 新编排：`build-tools/package.sh`；手动工作流维护源`build-tools/build-package.yml`；Dockerfile/源码锁为数据，安装核心统一在offline-runtime。
- 当前七源码HEAD与sources.json一致，七源码目录git status均为空。未更改业务源码/锁文件。
- 补充实际Docker-save归档config/标签/平台/镜像ID检查；不加载镜像、不启动产品容器。最终归档重新读取成员及摘要。
- 安装器接纳完整PACKAGED材料契约，不伪造READY证据；携带官方校验的Compose，明确不含Docker引擎/宿主OS。
- 旧workflow改为仅手动诊断；去除尚未推送的ISO下载/TCG启动步骤。不触及历史包、现有服务器、数据或CA卷。
- build-tools-old为既有用户整理结果，保持原样；旧历史执行证据不迁入本记录、不改字节。
- 状态：继续整批收尾，不把已知实现缺口交回用户；实际原生编译、组包、下载交付均未执行。目标安装、TLS/客户端/媒体未验证；本记录不声称已有完整交付。
- 辅助回归：WSL仅执行无Docker Python单元测试，38/38通过；bash -n通过；CI探测回归3/3通过。旧Windows回归曾因Linux路径/geteuid与过期mock失败，已在新测试副本适配，不改历史工具。
- 已修当前layout登记移除失效工具路径，登记统一入口及initialize；恢复当前服务端治理回归，不搬回旧工具或客户端版本状态。
- 已补配置生成与最终归档检查的实际Python执行回归（微型合成数据，不构建服务器包），覆盖七归档、JWT/补丁、端口、来源与归档摘要；不使用Docker。
- 已补业务Web same-origin构建参数，保留118工作区env；修正多模块Maven跳过测试参数，保留test-jar编译依赖；包内verify-only增加实际镜像归档验证。
- 新workflow经actionlint v1.7.12检查通过；保留同run/attempt artifact ID/digest来源记录。后续最终检查结果以实际输出为准。
- 最终复核：当前单元回归41/41、治理3/3、旧诊断探测回归3/3通过；layout、bash -n、actionlint及CI git diff --check均通过。34项受控输入源/CI字节一致，摘要同步后重核。
- 本轮脚本收尾已完成，未执行git提交/推送/Actions调度，没有新服务器包，不能把本轮辅助验证当作真实编译成功；真实原生构建结果由后续正常workflow运行给出，不新增安装测试门槛。
# 2026-11-12 固定证书标签维护工具同步

既有实例收回修复入口：tools/repair-creator-reclaim.py，默认检查模式；apply需管理员确认会议空闲。
配置转换两项单元回归通过，未在47执行预检查/修复，Docker命令和失败恢复未集成验证。
只修现有配套完整实例的收回开关与URL，不自动补装API、插件或改网关。

创建者收回修正：公共首次启动配置与转移成对默认开启，补齐host_reclaim_url。
WSL无Docker的test_offline_start.py六项通过；未更新47、未改历史包、未执行会议行为验收。

本地 cert-tool.py 新增 fixed-json 候选转换（外部 cert、内部 cert-inner），
新增 replace-fixed-cert.sh 用于已迁移且真实启动参数匹配的实例，仅更新外部证书引用。
旧换证/回滚入口增加启动参数检查。文档说明首次迁移、重建持久化、回滚及实际客户端验证边界。
cert 单元回归6项通过；未执行新换证脚本、未运行换证集成测试、未生成新更新包。
正式服务器构建/初始化链路尚未统一固定JSON，不宣称全链路完成。
47此前仅热加载JSON并修改Compose；当前容器旧启动参数尚未通过重建消除，
不能直接restart并假设保留固定标签。此次本地同步不连接或变更服务器。
# 2026-11-19 网络参数审计实现

本地实现七服务构建前参数扫描、固定源码端点清单、组包最终Compose检查，
JSON/Markdown随独立Actions审计制品及包provenance保存。新包首次启动
要求显式MEDIA_HOST并核对派生/映射，通用打包空值仅deferred。
双客户端增加源码清单、编译前临时配置核对、最终包检查与摘要审计。
源码清单review-required并非全部动态地址已审阅；未执行Actions或真实出包/安装。
测试细节见唯一知识库台账；历史output布局失败未删除或掩盖。

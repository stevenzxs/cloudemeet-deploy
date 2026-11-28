# CloudMeet unified client builder

## 2026-11-20 现行签名契约（覆盖下文历史Windows签名要求）

用户二次确认：Windows EXE/MSI不执行代码签名，不要求Windows PFX、SignTool、私有证书库访问或时间戳；Forge移除签名postPackage并直接保留maker-wix结果，不再调用签名postMake。最终检查/网络审计/交付不要求Windows签名，记录`signing: {required:false,status:"unsigned"}`，不生成`signature.passed`。交付README明确UNSIGNED EXE/MSI及未知发布者/SmartScreen风险；HTTPS CA信任不变，不能把摘要当签名或保证公众信任。

Android保持现有keystore、Actions Secrets安全注入和最终唯一批准DER SHA256核验，不换debug身份。两端继续检查实际版本、平台/ABI、入口、公开CA和摘要；安装/TLS/会议结果单列。原Windows工具/身份/Secrets保留为历史，不用于本入口，不自动删除。当前辅助回归不代替新Actions最终产品验包。

2026-11-23中文快捷方式回归修复：当前maker-wix显式使用`shortcutName: '云会议'`，并设置MSI中文代码页；不改变CloudMeet产品/安装身份或`cloudmeet.exe`。最终验包读取MSI `Shortcut`表，核对桌面、开始菜单两项的中文长名称及主程序目标，英文/缺项/重复项/错误目标立即失败。旧统一MSI脚本及旧测试不改；此修复没有重新构建或修改历史安装包，旧快捷方式残留和真实升级行为仍需另行实装核验。

规范见`../../AGENTS.md`。工具位于`deploy/skills/msi-build-deploy/tools/clients`，业务源码仍在deploy的同级目录。在工作区根执行时使用`deploy/skills/msi-build-deploy/tools/clients/build-clients.cjs`，Node无需新增依赖：

```powershell
node --test deploy/skills/msi-build-deploy/tools/clients/tests/*.test.cjs
node deploy/skills/msi-build-deploy/tools/clients/build-clients.cjs --target all --env-file "$PWD/deploy/skills/msi-build-deploy/config/client.env" --check
```

唯一配置为`deploy/skills/msi-build-deploy/config/client.env`，四项必填：SITE_DOMAIN、SITE_SCHEME、
SITE_PORT、CLIENT_VERSION。命令不接受其他配置路径或进程环境覆盖这四项。
可选CLIENT_CA_FILE指定公开CA，路径相对client.env；配置后必须存在且为有效CA，
不得包含私钥。预检查记录CA指纹/到期日，构建前复核未变化。
Electron打入client-trust.json/client-ca.crt，按配置入口使用严格CA校验；
Android临时注入raw/cloudmeet_client_ca.crt及主机限定network-security-config，
保留其他主机策略。不关闭证书链、有效期或主机校验。
CLIENT_VERSION为批准的三段基线；实际交付显示和平台数字字段由受控Run记录派生，不以手填补丁号递增代替修订号。
`--target`支持electron（Windows x64）、android、all；electron要求Windows主机，
android可在Linux构建（2026-11-20用户批准Actions android目标改跑ubuntu-24.04）。

## Android versionCode自动转换

基线1.0.21与数字基线1021绑定：显示1.0.21+rN，Android数字字段为 1021×1000 + N×10（每个修订号预留末位 patch 档）；r1=1021010、r10=1021100、r45=1021450。MSI=1.0.((21+N)×10)，PE增加第四段0。patch 发布（single-build-deploy 技能）占用末位1..9：显示1.0.21+r45-patch.1 → 1021451，MSI 1.0.661。
旧三段数字转换只用于诊断基线，不允许无分配记录正式打包。超过平台上限、历史最高版本
未核验或不满足升级单调性均阻断，不卸载/清数据绕过。
Actions提供`--version-record version-assignment.json`，校验配置SHA、Run、scope及源码SHA；
`--check`不分配修订号，无记录时报告诊断基线及缺项。配置策略已获用户批准启用，兼容基线限现存正式包；版本策略见`../config/version-policy.json`。

## 构建行为和限制

- 需要已安装的Electron/Android依赖、WiX、JAVA_HOME、ANDROID_HOME或ANDROID_SDK_ROOT。
  不自动安装工具、升级依赖或连接服务器。预检查不证明JDK/SDK具体版本可编译。
- Electron临时注入package.json版本及deployment.env，经cloudmeet.forge.cjs包装构建
  原生maker-wix MSI；2026-11-20用户批准移除OpenVPN集成，不再构建unified MSI，
  产品内VPN面板代码保留但无运行时（后续产品决策单独处理）。
  Android临时注入业务deployment.json与原生默认SERVER_URL，Gradle参数注入
  appVersion与cloudmeetVersionCode；保留已有企业受管配置功能。
- 正常成功/失败均恢复上述源文件原始字节。不改keystore或私钥；
  仅按CLIENT_CA_FILE注入目标入口的证书信任策略。
  强制杀进程/断电不能保证finally恢复；须人工核对源文件和锁后再构建。
- 候选及日志进入本机Temp/opencode/cloudmeet-clients-*，不进入release或旧debug目录。
  build.json记录状态、实际收集文件、字节数、SHA256；只收集本次时间范围产生的
  maker-wix MSI与release APK，旧文件不会被当作新构建成功。
  Android使用Gradle任务级`:app:packageRelease --rerun :app:assembleRelease`，
  强制本批重新打包APK，依赖编译仍可缓存；避免UP-TO-DATE旧时间戳被新产物检查拒绝。
- 编译结束仅为compiled-candidate-unverified。当前不自动提取二进制版本、验证
  签名或包内origin/ABI，不自动晋级交付。须逐项核验后才可交付到规范release路径。
- 正式客户端交付根为`deploy/release/clients/`，与`release/amd64/`、
  `release/aarch64/`同级；交付路径为`deploy/release/clients/<架构>/<批次>/`。
  预检查与build.json中的deliveryRoot明确记录该根目录，但不会自动创建或晋级。
  Windows x64使用amd64；多ABI APK必须注明全部实际ABI，不因存入aarch64就宣称仅ARM64。
  已有旧路径安装包不因本次同步而移动或改写。
- Android release签名配置必须存在；MSI缺批准PFX/公开身份即阻断，不允许未签名交付。
  新入口的私有CA/主机匹配兼容性未验证，不关闭全局证书校验。

WiX依次识别WIX/bin、WIX便携目录、PATH及默认v3.14/v3.11安装目录。
当前本机PATH已提供D:\tool\wix311-binaries，无需重复安装或修改系统环境。
这不是工具测试失败，也不代表MSI/APK已编译或安装验收。

## 平台与架构目录（覆盖上述旧架构路径）

## 打包交付终点（覆盖旧候选不晋级说明）

正常构建依次完成最终包检查及自动交付，Temp不再作为成功终点。
MSI管理解包后核对实际版本、PE架构、内嵌入口/公开CA以及MSI和主程序签名状态；
APK使用SDK工具核对版本、真实ABI、签名和打包资源中的入口/CA。
必需检查缺失或失败即报阻塞；Windows MSI及主程序须批准身份的有效签名和时间戳，APK比对批准签名DER SHA256。
通过后复制到release/clients/<平台>/<架构或ABI>/<批次>，生成证据、说明及SHA256SUMS。
交付目录拒绝覆盖。设备安装、线上TLS与会议媒体验收不属于打包门禁。
检查依赖Windows Installer管理解包、PowerShell、Python和Android SDK的
apkanalyzer/aapt/apksigner；管理解包仅展开MSI，不安装应用。

正式交付使用 `release/clients/windows/<x64|arm64>/<批次>/` 或
`release/clients/android/arm64-v8a/<批次>/`。
当前 Windows 仅构建 x64，不生成 x86；Android 只构建并交付 arm64-v8a APK。
候选使用相同平台/架构分类。
需要 Python 3 检查 APK ZIP 成员。
deliveryDirectory 仅记录目标模板，不自动晋级、不移动历史产物。
# Network audit (2026-11-19)

`--check` writes JSON/Markdown preflight and source-endpoint inventory to
`CLOUDMEET_AUDIT_DIR`, or a new temporary candidate/audit directory. Native builds
check temporary effective Electron deployment/trust and Android deployment,
managed SERVER_URL and host-scoped trust before compilation. Final package
checks are summarized with artifact hashes, copied alongside new deliveries
and covered by SHA256SUMS. Actions retains the audit directory even on failure.

Source literals are `review-required`: historical defaults, optional external
services and user/profile overrides are not silently declared safe or active.
Generated default endpoint checks do not prove installed-user overrides or all
runtime URL construction, TLS connectivity or meeting functionality.

Audit convergence: preflight and source inventories are staged byte-for-byte into
the build candidate and delivered with generated/final reports. Android inspection
now requires decoded XML: Manifest must reference the checked restrictions resource
and, for a private CA, the checked network-security resource; the exact host rule
must reference cloudmeet_client_ca. Raw AXML string-pool matches no longer qualify.
If the installed apkanalyzer omits domain text or cannot decode references, packaging
fails closed pending a verified decoder; no actual APK decoder acceptance is claimed.
The final React Native/Hermes bundle default and installed profile overrides remain
unverified. Signing execution on 150 is not implemented by these checks.

Second-review fix: resource IDs are resolved through `aapt dump resources`, and
`apkanalyzer resources value` obtains the actual (possibly shortened) XML/raw member.
The CA digest is checked only in that referenced raw member. A historical APK's
Manifest/restrictions mapping has been checked read-only with installed tools;
private-CA domain decoding acceptance remains separate from signature identity checks.

## 标准签名（2026-11-19，覆盖早期未签名说明）

`config/signing-policy.json`固定证书库工具提交、Android批准DER指纹和Windows身份路径。
`signing.cjs`只调用证书库工具，不复制签名实现。工作流检出受审证书库提交，要求真实
`windows/public/identity.json`、WINDOWS_PFX_BASE64、WINDOWS_PFX_PASSWORD、
CERTIFICATES_READ_TOKEN（仅证书库contents:read）及SignTool。缺项在构建前拒绝，不降级。
Forge postPackage签主程序，再调用产品原生统一MSI组包，之后签最终MSI；验包调用
SignTool与公开身份比较。APK要求唯一批准签名DER指纹，不接受仅Verifies。
当前真实Windows身份尚缺，固定工具提交下也无该身份；配置后必须更新受审工具SHA及
工作流引用再构建，不能临时覆盖身份。实际签名/时间戳/清理及最终包仍须云端验收。

## 实时日志与失败诊断（2026-11-20）

Android和Electron通过同一run入口将子进程stdout/stderr逐行实时输出至Actions控制台，
带`[client-build]`前缀，支持回车进度和退出末行。普通signing/password等错误描述保留，
只遮盖凭据值/私钥；Android已注入properties中的密码也按值遮盖，不转发到子进程环境。
脱敏audit日志完整追加保留（不限64KiB），失败摘要仍限尾部；超过1MiB的异常单行明确标记。
旧Run的固定提交不因本次修改而更新；本机辅助回归不等于新Actions产品验收。

子构建失败时，错误包含实际exit/signal或spawn错误码及脱敏后的最后30行（最多8KiB），
不再只指向Runner销毁后不可读取的临时文件。原始electron.log/android.log仍留受保护的
候选目录；不上传整个候选目录、命令参数或环境。脱敏屏蔽已知秘密值、明确凭据字段值及
私钥块；完整脱敏诊断以build-electron.log/build-android.log写入CLOUDMEET_AUDIT_DIR，
由工作流现有always审计制品保留14天。不要将秘密写入产品工具自定义日志；脱敏不是秘密管理替代品。

旧Run44023749308（配置e256f5d，2026-11-17）未上传任何artifact，其详细electron.log
无法从现有Run取回；只能确认Forge子进程失败，不能据此外层错误断言具体编译根因已修复。
重新运行旧Run仍使用旧workflow；本次仅补诊断辅助回归，不发起构建或绕过现有版本/签名门禁。

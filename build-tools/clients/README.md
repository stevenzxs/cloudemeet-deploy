# CloudMeet unified client builder

规范见`../../AGENTS.md`。工具位于deploy/build-tools/clients，业务源码仍在deploy的同级目录。在工作区根执行时使用deploy/build-tools/clients/build-clients.cjs，Node无需新增依赖：

```powershell
node --test build-tools/clients/tests/*.test.cjs
node build-tools/clients/build-clients.cjs --target all --env-file deploy/config/client.env --check
```

唯一配置为`deploy/config/client.env`，四项必填：SITE_DOMAIN、SITE_SCHEME、
SITE_PORT、CLIENT_VERSION。命令不接受其他配置路径或进程环境覆盖这四项。
可选CLIENT_CA_FILE指定公开CA，路径相对client.env；配置后必须存在且为有效CA，
不得包含私钥。预检查记录CA指纹/到期日，构建前复核未变化。
Electron打入client-trust.json/client-ca.crt，按配置入口使用严格CA校验；
Android临时注入raw/cloudmeet_client_ca.crt及主机限定network-security-config，
保留其他主机策略。不关闭证书链、有效期或主机校验。
三段数字版本按原值使用，遵守MSI上限255.255.65535，不自动增加补丁号。
`--target`支持electron（Windows x64）、android、all；当前实现要求Windows。

## Android versionCode自动转换

唯一读取CLIENT_VERSION，规则为`major * 1000 + minor * 100 + patch`：
`1.0.19 → 1019`、`1.1.0 → 1100`、`2.0.0 → 2000`。
minor限定0..9，patch限定0..99以避免编码冲突；越界拒绝Android构建。
相同版本重复构建得到相同code，不自动递增，不读取历史证据、时间计数或
release-version.json。保留独占构建锁，但不创建版本状态文件。
旧时间计数APK的code可能更大，覆盖升级不保证；提示风险但不阻止编译，
不自动卸载应用或清数据。仅在已获构建授权且检查通过后执行不带--check的命令。

## 构建行为和限制

- 需要已安装的Electron/Android依赖、WiX、JAVA_HOME、ANDROID_HOME或ANDROID_SDK_ROOT。
  不自动安装工具、升级依赖或连接服务器。预检查不证明JDK/SDK具体版本可编译。
- Electron临时注入package.json版本及deployment.env，运行现有Forge统一MSI钩子。
  Android临时注入业务deployment.json与原生默认SERVER_URL，Gradle参数注入
  appVersion与cloudmeetVersionCode；保留已有企业受管配置功能。
- 正常成功/失败均恢复上述源文件原始字节。不改keystore或私钥；
  仅按CLIENT_CA_FILE注入目标入口的证书信任策略。
  强制杀进程/断电不能保证finally恢复；须人工核对源文件和锁后再构建。
- 候选及日志进入本机Temp/opencode/cloudmeet-clients-*，不进入release或旧debug目录。
  build.json记录状态、实际收集文件、字节数、SHA256；只收集本次时间范围产生的
  unified MSI与release APK，旧文件不会被当作新构建成功。
  Android使用Gradle任务级`:app:packageRelease --rerun :app:assembleRelease`，
  强制本批重新打包APK，依赖编译仍可缓存；避免UP-TO-DATE旧时间戳被新产物检查拒绝。
- 编译结束仅为compiled-candidate-unverified。当前不自动提取二进制版本、验证
  签名或包内origin/ABI，不自动晋级交付。须逐项核验后才可交付到规范release路径。
- 正式客户端交付根为`deploy/release/clients/`，与`release/amd64/`、
  `release/aarch64/`同级；交付路径为`deploy/release/clients/<架构>/<批次>/`。
  预检查与build.json中的deliveryRoot明确记录该根目录，但不会自动创建或晋级。
  Windows x64使用amd64；多ABI APK必须注明全部实际ABI，不因存入aarch64就宣称仅ARM64。
  已有旧路径安装包不因本次同步而移动或改写。
- Android release签名配置必须存在；MSI未配置PFX时可能无签名，不能声称已签名。
  新入口的私有CA/主机匹配兼容性未验证，不关闭全局证书校验。

WiX依次识别WIX/bin、WIX便携目录、PATH及默认v3.14/v3.11安装目录。
当前本机PATH已提供D:\tool\wix311-binaries，无需重复安装或修改系统环境。
这不是工具测试失败，也不代表MSI/APK已编译或安装验收。

## 平台与架构目录（覆盖上述旧架构路径）

## 打包交付终点（覆盖旧候选不晋级说明）

正常构建依次完成最终包检查及自动交付，Temp不再作为成功终点。
MSI管理解包后核对实际版本、PE架构、内嵌入口/公开CA以及MSI和主程序签名状态；
APK使用SDK工具核对版本、真实ABI、签名和打包资源中的入口/CA。
必需检查缺失或失败即报阻塞；未签名MSI明确记录，异常签名拒绝。
通过后复制到release/clients/<平台>/<架构或ABI>/<批次>，生成证据、说明及SHA256SUMS。
交付目录拒绝覆盖。设备安装、线上TLS与会议媒体验收不属于打包门禁。
检查依赖Windows Installer管理解包、PowerShell、Python和Android SDK的
apkanalyzer/aapt/apksigner；管理解包仅展开MSI，不安装应用。

正式交付使用 `release/clients/windows/<x64|arm64>/<批次>/` 或
`release/clients/android/<armeabi-v7a|arm64-v8a|x86_64|universal>/<批次>/`。
当前 Windows 仅构建 x64，不生成 x86；Android 读取 APK 实际 ABI，多 ABI 使用
universal 并记录完整集合，不代表支持所有 ABI。候选使用相同平台/架构分类。
构建临时排除 Android x86，结束恢复源码。需要 Python 3 检查 APK ZIP 成员。
deliveryDirectory 仅记录目标模板，不自动晋级、不移动历史产物。

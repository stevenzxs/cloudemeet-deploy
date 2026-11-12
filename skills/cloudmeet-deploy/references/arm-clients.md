# ARM 与客户端注意事项

唯一完整规范为 `deploy/AGENTS.md`，README仅导航，本文件仅提供操作方法。已发布包按包内实测入口使用，`deploy/config/jitsi-base.yaml` + `deploy/config/docker-compose.yml` 为过渡模板，运行项目根仍为deploy。客户端构建入口为 `build-tools/clients/build-clients.cjs`。不依赖根级历史部署目录。

## ARM

- 核对实机 aarch64、每项镜像 manifest/digest；业务 JAR/dist 在开发机构建，运行镜像也须支持 ARM64。
- openEuler 须同时具备 Docker engine 和 client，不照搬 Ubuntu apt。Compose 二进制校验来源、架构、摘要。
- 根模板可能挂载 JAR/dist，源码镜像也可能已内置；先核对实际实例及来源路线，不能默认互换或遮盖已构建产物。目录使用aarch64，OCI平台通常标作linux/arm64，二者须正确映射。
- 离线下载工具为 `deploy/tools/fetch-image.py`，先读参数，校验 manifest/layer 和完整 tar 后导入。
- 历史 ARM HTTP 是云接入备案/TLS 重置下的批准测试，不是 ARM 要求。域名公共 HTTPS、IP 私有 CA、HTTP 测试分别审查。
- HTTP 专用 iframe 副本在 `deploy/patches/optional-http/external_api.js`，默认不挂载；见补丁说明。HTTP 普通浏览器媒体限制不能用全局 bypass 掩盖。
- Prosody UID/GID、品牌/CSS、运行配置及真实媒体检查见主文档。

## 客户端

唯一配置源为`deploy/config/client.env`，只含下列公开参数；实际值读取该文件，不在技能中保存实例默认地址：

```dotenv
SITE_DOMAIN=<客户端实际访问的外层IP或域名，不含协议和端口>
SITE_SCHEME=https
SITE_PORT=<外层访问端口>
CLIENT_VERSION=<三段数字发布版本>
```

MSI/APK共用此入口；不得从服务端target.env、.env、旧client.env、进程环境或源码默认值覆盖/回退。无效或缺项必须拒绝打包。服务端通配监听不代替客户端首次寻址。

CLIENT_VERSION为唯一发布版本来源，按原值用于Electron产品版本和Android versionName；Android versionCode按major×1000+minor×100+patch转换，例如1.0.19对应1019。minor限0..9、patch限0..99，避免冲突；越界拒绝Android构建。相同版本得到相同code，不自动递增，不读取历史证据、时间计数或release-version.json。旧时间计数APK可能无法覆盖升级，提示但不阻止编译，不自动卸载或清数据。构建manifest记录两者，实例具体版本读取配置，不设技能默认值。

统一入口已恢复四项配置读取及候选构建编排；不得绕过统一入口直接运行Forge/Gradle充当正式发布。--check只读，不启动构建或写版本状态；真实构建须已有授权并通过预检查。详见工作区build-tools/clients/README.md。

在工作区根运行（第二条仅在获得构建授权后执行）：

```powershell
node build-tools/clients/build-clients.cjs --target all --env-file deploy/config/client.env --check
node build-tools/clients/build-clients.cjs --target all --env-file deploy/config/client.env
node --test build-tools/clients/tests/*.test.cjs
```

配置接受 IPv4/DNS 和 SITE_SCHEME/SITE_PORT；核对完整origin及Electron的`/cm/desktop`入口。新私有CA必须适配客户端限定信任策略；服务端使用本地兜底证书、用户接受浏览器告警，不代表MSI/APK可接受证书主机不匹配。兼容性须明确报告，禁止全局证书bypass。

Electron 需要 WiX v3、SDK/.NET 和合法 OpenVPN payload；Android 需要 JDK17、SDK35/Build Tools35 和项目指定 NDK。禁止并发构建、删除活动锁；强制中断后检查入口配置恢复。

WiX自动依次识别WIX/bin、WIX本身的便携目录、PATH、默认v3.14/v3.11目录；先检查已有工具，勿重复安装或全局修改环境。编译器candle.exe和链接器light.exe均须可用。预检查通过不证明完整工具链可完成编译。

唯一新增交付位置为 `deploy/release/<架构>/clients/<批次>/`，按客户端自身OS/ABI归类，多ABI如实登记，明确签名及已验范围。恢复的本机构建器将候选、日志和build.json保留于Temp/opencode/cloudmeet-clients-*，不另建debug目录、不再输出旧history/client-builds、不自动晋级release。build.json记录编译状态与产物摘要，但不自动验证二进制版本、包内origin/ABI或签名，交付前须分别核验。旧材料不自动移动或删除。MSI安装升级、VPN、卸载须隔离环境验收，不自动卸载开发机旧版本；安装运行与真实会议分别报告。

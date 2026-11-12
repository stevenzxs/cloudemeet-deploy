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

在工作区根运行，显式指定本次客户端配置：

```powershell
node build-tools/clients/build-clients.cjs --target all --env-file deploy/client.env --check
node build-tools/clients/build-clients.cjs --target all --env-file deploy/client.env
node --test build-tools/clients/tests/*.test.cjs
```

配置接受 IPv4/DNS 和 SITE_SCHEME/SITE_PORT；核对完整 origin。新私有 CA 必须适配客户端限定信任策略，不是只换环境变量。

Electron 需要 WiX v3、SDK/.NET 和合法 OpenVPN payload；Android 需要 JDK17、SDK35/Build Tools35 和项目指定 NDK。禁止并发构建、删除活动锁；强制中断后检查入口配置恢复。

唯一新增交付位置为 `deploy/release/<架构>/clients/<批次>/`，按客户端自身OS/ABI归类，多ABI如实登记，明确签名及已验范围；候选留在Actions，不另建debug交付树。当前构建器仍输出 `deploy/history/client-builds/<批次>/`，属于尚未适配的内部构建路径，旧根clients未迁移；不假称输出已切换，不自动移动/删除其他旧材料。核对manifest/摘要/签名，不能以release目录或旧文件名推断资格。MSI安装升级、VPN、卸载须隔离环境验收，不自动卸载开发机旧版本；安装运行与真实会议分别报告。

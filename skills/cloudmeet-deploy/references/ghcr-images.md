# GHCR 候选镜像与运行契约

当用户选择已发布镜像、GHCR或“使用这些镜像”时读取本文件。它不是自动部署授权，也不是生产安全批准。

## 1. 批次与身份

- 仓库前缀：`ghcr.io/stevenzxs/`。
- 分发标签：`11248-cm.20261110-rc1-amd64`；不使用 `latest`。
- 平台：仅 `linux/amd64`。ARM64 后续单独处理，不在本批适配、构建或模拟范围内。
- 标签表示分发批次，不表示所有组件同日构建、同一源码版本或已完成七服务组合验收。
- 表中摘要为已发布远端身份；部署使用 `ghcr.io/stevenzxs/<镜像>@sha256:<摘要>`。部署前重新核对远端身份/平台和完整层拉取，禁止覆盖不同身份的既有RC标签。

| Compose服务 | 镜像 | 已核对的远端SHA256 | 原始来源标签（本地证据，不是目标拉取地址） |
|---|---|---|---|
| gateway | cloudmeet-caddy | `d264ac6b8061f761cac0e3fa58dfe6ebe57485fdda991017086af72b406aef05` | cloudmeet/caddy:source-20261109-0d98cae |
| app-web | cloudmeet-app-web | `2f3e53007deb13b39736f8d36d663a923e822022438d1fb1aad819d77599b83f` | cloudmeet/app-web:candidate-20261109-dfe8d50-nginx1306-osfix |
| api | cloudmeet-api | `236223742a990785565e893b21276ae50a0842eb1fc813cb35c40a16472a386f` | cloudmeet/api:source-20261109-2178607 |
| web | cloudmeet-web | `b65f0c94558224e23444463cffc40c463362aff9a8da665903698fa096e14c49` | cloudmeet/web:source-11248-jks-20261110 |
| prosody | cloudmeet-prosody | `60a3d5ec1554120133ee58e999b87be4cb1cefa083063fb7f036c1f6bc197bf2` | cloudmeet/prosody:source-11248-jks-20261110 |
| jicofo | cloudmeet-jicofo | `e2e32bf955349a35f14920ed9c74a9be4a2cfafe148f0d04a36f01ffe120f2f6` | cloudmeet/jicofo:source-11248-jks-20261110 |
| jvb | cloudmeet-jvb | `4c88d425b15cd185d284b9c6252e4d73f9cb23732d560b898c847cb6687e99cf` | cloudmeet/jvb:source-11248-jks-20261110 |

发布证据（相对工作区根）：
- 六应用镜像：`deploy/history/deployments/20261110-jks-118/ghcr-retry-20261110/attempt-20261110T054238028795Z/result.json`。
- Caddy：`deploy/history/deployments/20261110-jks-118/ghcr-caddy/` 下独立attempt结果。
- 截至2026-11-10，七个包均已推送并核对远端身份；前六及Caddy分别实测匿名manifest HTTP200。Web/Prosody另有匿名config读取通过证据。其他组件匿名config及七镜像完整层匿名拉取未作为全批次门禁执行。
- 已知漏洞风险仍保留，app-web的blocked-not-cleared不得改为已接受；不因发布或Public设置宣称安全放行。

## 2. 必须适配的运行配置

根 `deploy/jitsi-base.yaml` 与 `deploy/docker-compose.yml` 是过渡模板，不是本批完整registry部署入口。为本次目标生成独立最终Compose或经过验证的override；检查合并结果，而非仅检查源文件。

1. **七个完整image引用**：逐项替换并锁digest。现有模板拼出`<repo>/web`，本批名为`<repo>/cloudmeet-web`，只设置JITSI_IMAGE_REPO无法正确映射。不得静默保留官方11146应用镜像。
2. **API**：镜像ENTRYPOINT已是`java -XX:MaxRAMPercentage=65 -jar /app/app.jar`。删除旧Compose `command`（合并结果为null/无额外命令），去掉`./artifacts/app.jar:/app/app.jar`；保留`/app/data` SQLite及`/data/banner-logos`会标挂载和匹配的JWT/DB环境。旧命令会追加到ENTRYPOINT，旧JAR挂载会遮盖已发布产物。
3. **业务Web**：镜像内置`/usr/share/nginx/html/cm`和Nginx配置，去掉旧`./artifacts/dist`与`./artifacts/nginx.conf`挂载；保留会标只读共享等所需数据。VITE是构建期参数，不承诺运行时换env即可改前端入口；对实际页面/API/external_api/iframe同origin做检查。
4. **Caddy**：使用gateway映射，保留实际Caddyfile和`/data`、`/config`持久卷。现有根Caddyfile为IP HTTPS私有CA（tls internal），不是任意域名公网证书模板。域名证书、DNS-01、端口另按本次配置验证；DNS-01需核实实际模块，不能假定镜像自带。增量部署保留CA卷，不重置旧客户端信任。
5. **Jitsi四服务**：核对本批生命周期模板、read_only/tmpfs、XMPP凭据与配置目录；按实际UID/GID初始化目录。保留条件适用的品牌/CSS及JWT角色持久补丁，不能因镜像已发布而省略或重复注入。Jicofo自动owner必须与主持人方案一致。
6. **网络**：按本次origin配置PUBLIC_URL、网关路由与外部端口；JVB_ADVERTISE_IPS指向真正可达媒体地址，UDP映射按实例设置。管理端口不公网暴露；不沿用历史IP、临时测试internal网络或无宿主端口配置。

若用Compose `!reset`/`!override`移除旧command/volumes，先核实目标Compose支持并验证展开结果；不支持时生成独立最终文件，不能保留旧挂载“先启动试试”。现有集成准备脚本仅可参考去覆盖逻辑，其旧镜像列表与测试网络不是本批生产配置。

## 3. 部署前和验收门禁

- 本地配置检查：七服务与上表逐项映射；平台amd64；完整digest；无build；无旧JAR/dist/nginx覆盖；API无额外command；数据/CA卷保留；补丁及入口参数明确。检查过程不输出展开后的秘密。
- 在授权目标实际拉取并验证全部层、平台和身份，再执行批准的最小切换。匿名失败先区分包可见性/权限/网络；不重新构建代替失败的拉取。
- 依技能主流程验证：严格TLS/业务页面/API、真实BOSH或WebSocket、JWT主持人OWNER/普通PARTICIPANT、Jicofo可用桥，最后多端双向媒体/ICE。启动成功、清单200、UDP监听均不能代替这些验收。
- 记录registry index/platform manifest/config/engine Id的类型关系。containerd可能以index digest作为engine Id；不能拿index与config作直接相等比较而误报发布失败。
- 回滚保留旧digest、最终Compose、配置及一致性数据备份；不将新数据随意覆盖为旧备份，不删CA卷或其他实例资源。

# CloudMeet Actions compilation and packaging

唯一维护源为部署仓库中的本目录；部署规范见 `../AGENTS.md`。工作区不需Docker。Actions从同一提交检出工作流、build-tools、config及patches，不再人工同步CI分支副本。

## 唯一正常入口

本节是服务端Actions入口；Windows MSI/Android APK的独立本机构建入口为
`clients/build-clients.cjs`，配置唯一读取`deploy/config/client.env`，先运行
`node build-tools/clients/build-clients.cjs --target all --check`。
版本状态证据、工具链及候选验证边界见[客户端工具说明](clients/README.md)。

将本目录受控同步至部署仓库的 `build-tools/`，将 `build-package.yml` 同步至
`.github/workflows/build-package.yml`；公开补丁仍来自部署仓库 `patches/`。
审核并提交推送这些文件后，在 GitHub Actions 选择 **CloudMeet compile and package aarch64**：

- `version`：本次版本，如 `1.0.19-rc1`（不代表已占用客户端版本）。
- `material_commit`：包含本次脚本、补丁及配置的完整40位提交SHA，必须等于所选workflow提交。
- 地址与端口：`config/target.env`不绑定网页入口IP，仅设置协议、端口及可选媒体IPv4覆盖。Caddy使用本地证书和通配路由，接受证书告警/客户端兼容性限制；信令由启动器生成的custom-config.js跟随浏览器入口。`config/jitsi.env`保留公共参数。

工作流只读仓库，不需要SSH或registry秘密，不自动发布镜像。每次run/attempt完整编译七服务；
当前CI分支尚未进入默认分支，限定push触发仅在ci/arm64-smoke分支修改新workflow文件时运行，默认版本1.0.19-rc1、材料SHA为该提交，目标来自受控config/target.env；其他修改不自动构建。
失败则无最终包，不跨run/attempt补旧镜像。**重跑请选择全部jobs**，不能仅重跑失败job后混用旧attempt。
Docker build中的依赖和构建层缓存允许复用，但输出应用镜像必须由本批build步骤产生。

`package.sh build SERVICE`构建一个锁定源码服务，输出`output/SERVICE/{SERVICE.tar.gz,SERVICE.json}`。
`package.sh assemble`仅接收本run/attempt的`incoming/SERVICE/`，执行材料检查、生成最终包。
这两个命令由工作流设置VERSION、BATCH和GitHub运行身份；不在Windows/WSL运行服务器构建或组包。

## 输出及安装边界

最终artifact `cloudmeet-aarch64-RUN-ATTEMPT` 包含：

- `cloudmeet-BATCH-aarch64.tar.gz`及独立`.sha256`；
- `package-evidence.json`，只报告材料检查，不是安装或会议验收。

包内有七镜像、源码/镜像来源、Compose、配置、公开补丁、INSTALL、SHA256SUMS及公共安装核心。
目标需预先具备匹配Linux/aarch64 Docker Engine与Python≥3.7；本包不含Docker或宿主OS。
安装仅由用户按包内INSTALL显式运行；不联网补依赖、不build/pull、不覆盖既有env/data。
安装/客户端/媒体后续单独验收，镜像发布必须使用本包原镜像而非重建。

下载后在`deploy/release/aarch64/server/BATCH/`保留原artifact包，先核对外层归档SHA256，
再核对解包的SHA256SUMS；给出实际路径与来源后才称交付完成。下载不在此编译脚本中隐式执行。

## 维护验证（均无Docker）

```text
wsl -d Ubuntu-24.04 -- bash -n /mnt/d/code/jitsi/build-tools/package.sh
wsl -d Ubuntu-24.04 -- python3 -B -m unittest discover -s /mnt/d/code/jitsi/build-tools/tests -p test_*.py
python -B deploy/tools/check-deployment-layout.py
```

修改受控输入后重新生成`inputs.sha256`并核对CI副本；禁止手工跳过校验。
新工作流不调用旧诊断工作流。`build-tools-old/`和历史包保留，不作为本入口的运行依赖。
## 主持人转让默认集成（2026-11-12）

按用户确认及 `../AGENTS.md`，所有新正常部署默认开启主持人转让。`package.sh` 外置交付公开插件及引用，`offline-runtime/initialize.py` 目标生成API共享鉴权秘密和内部TLS材料，`offline-runtime/start.py` 安装插件并生成模块/接口配置。网关内部HTTPS不发布宿主端口，公网拒绝内部接口，Prosody严格验证CA。私钥及实例秘密不进镜像或包；不能以首次初始化覆盖已有实例。

找回及管理员恢复仍默认关闭，必需材料或配置缺项报错，不静默降级。包级校验与部署后轮换/撤权/接收确认/恢复验收分开。当前代码仍在收尾，CI受控副本/摘要及完整回归待核对；不表示已构建或已启用。继续使用Actions原生aarch64七服务主流程，不新增补丁交付线。
# Native architecture selection (2026-11-13)

## Target-side private certificate input

Actions outputs setup.py and setup.py.sha256 alongside the server archive and its checksum.
Do not upload cert.tar.gz to Git/Actions. Copy it securely beside those files on target.
After checking both SHA256 sidecars, run:
`sudo python3 -B setup.py --server-package <server.tar.gz> --verify-origin https://<host>:<port>`.
setup refuses an existing installation directory. It stages cert.tar.gz and cert/ without
changing the original package SHA256SUMS; the verifier permits only exact certificate
members matching the checked archive. Certificate SAN, expiry, chain and key are checked
before image imports. After startup only gateway is restarted; strict TLS/2xx verification
uses ca.crt and the explicit origin. Failures preserve secrets/data for manual recovery.
No automatic retry of first-install, target cleanup or server operations during packaging.

The single workflow accepts `architecture: amd64|arm64` (default arm64).
amd64 uses native ubuntu-24.04; arm64 uses native ubuntu-24.04-arm.
`TARGET_ARCH` controls the runner check, image platform, Java/Go toolchain,
bundled Compose, archive identity and Linux existing-engine target profile.
No emulation, local Docker, registry publication or target installation is part of packaging.
The Jitsi stable-11248 base is pinned to its multiarch index; its ARM child remains unchanged.

# CloudMeet Actions compilation and packaging

维护源为本目录；部署规范唯一见 `../deploy/AGENTS.md`。工作区不需Docker。

## 唯一正常入口

将本目录受控同步至部署仓库的 `build-tools/`，将 `build-package.yml` 同步至
`.github/workflows/build-package.yml`；公开补丁仍来自部署仓库 `patches/`。
审核并提交推送这些文件后，在 GitHub Actions 选择 **CloudMeet compile and package aarch64**：

- `version`：本次版本，如 `1.0.19-rc1`（不代表已占用客户端版本）。
- `material_commit`：包含本次脚本、补丁及配置的完整40位提交SHA，必须等于所选workflow提交。
- `origin`：默认 `https://47.110.84.166:8443`；HTTP重定向8080、媒体UDP10000。

工作流只读仓库，不需要SSH或registry秘密，不自动发布镜像。每次run/attempt完整编译七服务；
当前CI分支尚未进入默认分支，首次启动使用限定push触发：仅ci/arm64-smoke分支修改新workflow文件时运行，默认版本1.0.19-rc1、材料SHA为该提交、origin为已确认47入口；其他修改不自动构建。
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

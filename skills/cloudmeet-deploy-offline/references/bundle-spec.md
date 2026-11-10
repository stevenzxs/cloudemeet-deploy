# 离线包结构与安装器规范

本文档定义离线包的目录结构、manifest 格式、安装器行为与回滚要求。每次打包以 SKILL.md 第 2 节的本次清单为准；本文档是结构规范，不是内容默认。

## 当前工作区落地约束

交付根固定为 `deploy/`，成品 `packages/<版本>/`、证据 `history/`、验收客户端 `clients/`、技能 `skills/`。构建脚本在 `build-tools/`，不要把中间产物散落到工作区根。
下方树为通用示意，不要求为“对齐目录”重写已验收安装器。2026-11-09实测包用逐服务 `.tar.gz`、根级三Compose和 `install.py/engine.py/deploy.py`，实际入口以该包 `INSTALL.md` 为准；不得假称它包含未实现的 `uninstall.sh`、签名或zstd工具。
任何结构/运行内容变化须新版本重新校验；历史证据、已发布清单及包内脚本不为路径归并而修改。只改门禁状态不能获得安装资格。

## 1. 包目录结构

```text
cloudmeet-offline-v{版本}-{arch}/
├── images/
│   ├── images-{arch}.tar.zst        # docker save 输出，zstd 压缩
│   └── images.manifest.json         # 镜像身份清单（见第 2 节）
├── compose/
│   ├── jitsi-base.yaml
│   ├── compose.yaml                 # 按本次服务范围渲染
│   └── Caddyfile                    # gateway 为 Caddy 时
├── config/
│   ├── jitsi.env.example
│   ├── server.env.example           # 真实秘密安装时生成/收集，绝不随包
│   └── artifacts/                   # 补丁工件（按 P 编号子目录），含各自 SHA256 与来源说明
├── clients/                         # 可选：Electron MSI / Android APK 及各自摘要
├── bin/
│   ├── {arch}/docker-compose        # 静态二进制兜底，附官方来源摘要
│   └── {arch}/zstd                  # 目标侧无 zstd 时的解压兜底
├── install.sh
├── uninstall.sh
├── docs/
│   ├── 安装手册.md                   # 含摆渡、分卷还原、验收签字流程
│   ├── SBOM.spdx.json               # compliance.sbom=true 时
│   └── 漏洞扫描报告.md               # compliance.vuln_scan=true 时，附 trivy 离线库版本
├── SIGNATURES/                      # compliance.sign=true 时：签名与验证公钥（私钥绝不随包）
├── SHA256SUMS                       # 包内全部文件（自身除外）的 SHA256
├── REPORT.txt                       # 构建时间、构建机指纹、来源 digest 汇总、未决项
└── VERSION                          # 包版本、基线版本（增量包）、目标架构、origin 模式
```

分卷时最外层按 `包名.tar.zst.part-aa/ab/...` 切分，附 `SHA256SUMS.parts`；安装手册写明 `cat part-* > 包名.tar.zst` 还原步骤。

## 2. images.manifest.json

```json
{
  "bundle_version": "v2026.11.07-1",
  "bundle_type": "full",
  "base_release": null,
  "arch": "amd64",
  "origin_mode": "install-time",
  "created_at": "构建时间 ISO8601",
  "images": [
    {
      "name": "ghcr.io/jitsi/jvb",
      "tag": "stable-11146-2",
      "digest": "sha256:...",
      "platform": "linux/amd64",
      "size_bytes": 0,
      "source": "拉取来源仓库或构建记录路径",
      "patches_included": ["P04"],
      "verify": "load 后 docker inspect 复核 digest 的命令"
    }
  ]
}
```

每镜像必须有 digest 与 platform；增量包在 `base_release` 写明基线版本及逐镜像基线 digest，并只含相对基线变化的镜像/工件，安装器按基线 digest 校验目标机现状后才允许应用。

## 3. install.sh 行为规范

按以下顺序执行，任何一步失败即中止并输出证据，不留半成品状态：

1. **预检**：`uname -m` 与包架构一致；时钟偏差超过 120 秒直接中止并提示先配 NTP（内网证书与 JWT 的头号故障源）；可用磁盘 ≥ 镜像展开后 2 倍。
2. **引擎探测**：依次探测 `docker`（含 compose 插件）、`podman`、`iSulad`；均无则使用 `bin/` 兜底或明确中止并输出安装指引，不静默从包外下载任何东西。
3. **完整性校验**：`sha256sum -c SHA256SUMS` 全量通过后才允许 load；签名启用时先验签。
4. **导入**：`zstd -d | docker load`（或引擎对应命令），逐镜像复核 digest 与 manifest.json 一致。
5. **配置渲染**：install-time 模式交互收集 origin（协议/IP 或域名/端口），渲染 env；烘焙模式直接校验预渲染值。渲染结果回显脱敏摘要供确认；发现占位符残留即中止。
6. **启动**：生成新秘密与私有 CA（CA 私钥只留在目标机卷内），`compose up -d`。
7. **冒烟**：容器无重启循环、网关 TLS 可用、API health UP、信令握手（BOSH 或 WebSocket 按本次模式）；结果写入 `验收报告.txt`（时间、版本、各项预期/实际/证据），供甲方签字归档。
8. 会议真实媒体、权限角色等联合验收不在安装器范围，报告中标"未验证"，须另行安排真实多端会议验收并记录证据。

## 4. uninstall.sh 与回滚

- 仅识别并移除本包创建的 Compose 项目、专属卷与导入的镜像（按 manifest digest 精确匹配）；禁止全局 prune、禁止无范围 `down -v`、不动共享网关/证书/无关业务。
- 卸载属破坏性操作：执行前集中展示将删除/保留清单（目录、容器、卷、镜像及数据类别）、备份状态与数据丢失风险，要求现场明确确认；未确认、含糊回复或备份未完成不执行。清理范围发生实质变化时重新确认，不沿用旧确认。
- 增量更新包回滚 = 重新 load 基线 digest 镜像并重启对应服务；安装器在应用增量前记录当前 digest 作为回滚点。

## 5. 摆渡与审计要求

- 包经 U盘/光盘/网闸传输后，目标侧第一件事是验签+SHA256 全量校验，记录核验人与时间（建议写入验收报告，双人核验为推荐 SOP）。
- `REPORT.txt` 含构建机指纹（主机名/用户/时间）与全部来源 digest，供甲方追溯；不含任何秘密与私钥。
- SBOM 与漏扫报告标注工具及数据库版本日期；离线库过期时如实注明，不把旧库扫描结果说成最新结论。

## 6. 两阶段离线首装证据

- 制作阶段记录构建／导出主机及目标系统/架构；全包先下载至本地，重算摘要，再重新上传到用户指定验证机。两种主机可相同或不同，不默认115或amd64。
- 带Docker安装能力时，包中需含目标系统/架构匹配的Engine、CLI、containerd、Compose及完整必要依赖和离线安装说明；仅携带docker-compose二进制不算Docker离线安装包。
- 清理现有服务和卸载Docker属于第二阶段部署执行，须完成备份与集中二次确认后进行，不能由install.sh默认删除旧实例或运行环境。
- 证据分别记录：本地/远端包摘要、清理前后环境、Docker/Compose首装、空缓存镜像导入、禁止外网下载措施、服务冒烟及网络限制恢复。缺一项不扩大宣称；旧Docker或镜像缓存复用须明确披露。
- 验证机更换为ARM或其他发行版后，重新核对镜像和安装依赖；不能直接沿用amd64/Ubuntu包。真实会议联合验收另列，不能用启动或health替代。

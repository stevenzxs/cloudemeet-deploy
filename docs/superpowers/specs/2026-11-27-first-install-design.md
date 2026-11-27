# first-install 设计：GHCR 在线首装 + 启动验证

日期：2026-11-27
状态：待批准

## 意图

在用户指定的服务器上，用已发布批次的 GHCR digest 镜像首次安装 CloudMeet，并在安装后验证服务成功启动。技能完全自包含（`skills/first-install/`）：安装器本体来自已发布包内（包内含 compose/config/patches/runtime），技能侧只做编排，不导入任何其它技能目录的代码。

## 用户已定决策

- 材料：在线 GHCR digest（`setup.py --server-package <离线包> --registry registry.json --registry-sha256` 路线；离线包提供 compose/config/patches，镜像在线按 digest 拉取）。
- 验证范围：容器 + TLS + HTTP；不含登录/JWKS/信令/非 P2P 媒体。
- Docker 缺失即停止。
- 自包含拷贝（技能侧工具独立）。

## Goals

- SSH 驱动（同 full-clean 模式）：指纹确认、BatchMode、密钥认证；秘密不进入命令行/聊天输出。
- 材料获取：本机 `gh release download <tag>` 取服务端包 tar.gz + `.sha256` + `registry.json` + `.sha256`，逐侧车校验后 scp 上传；不得跳过摘要或用 `-k`。
- 预检（目标机，缺一即停）：uname 架构与包一致、Docker Engine + compose plugin、Python ≥3.7、TCP 443/80 与 UDP media 端口空闲、系统时钟偏差、磁盘；`caddy-public-acme` 另查 origin DNS 指向本机、443 可达预期、出站 DNS/HTTPS。
- target.env：实例配置存于包外绝对路径（用户给定），含 MEDIA_HOST（显式可用地址）。
- `private-ca`：cert.tar.gz 由用户经独立安全渠道提供并上传；`caddy-public-acme` 不需要。
- 安装：`sudo python3 -B setup.py --server-package … --verify-origin <origin> --target-env <abs> --registry … --registry-sha256 …` 远程执行；拒绝既有解包目录时停止，不删除重试。
- 验证：compose project 全部服务 running；TLS 握手与证书链/SAN/有效期（public ACME 用系统信任，private-ca 用提供 CA）；HTTPS GET `https://<origin>/` 与 `/cm/desktop/` 期望 200 且无重定向链。逐项报告 pass/fail，绝不暗示媒体验收。

## Non-goals

- 不装 Docker Engine、不做离线包路线、不做媒体/媒体客户端验收、不做升级（升级是另一条路径）。
- 不输出秘密、不轮换秘密、不触碰实例以外的资源。

## 文件

```
skills/first-install/
  SKILL.md
  tools/first_install.py    # 自包含编排：材料校验、上传、SSH 预检、远程 setup.py、启动验证
  tests/test_first_install.py
```

## 必须停止并报告

- 指纹/SSH 失败；材料清单/摘要缺失或不符；registry digest 与发布记录不符。
- 预检任一项失败（架构、Docker、Python、端口、时钟、ACME 前置条件）。
- setup.py 拒绝（既有目录、校验失败）；任一容器未 running；TLS/HTTP 任一项失败。
- 请求超出"首装+启动验证"终点。

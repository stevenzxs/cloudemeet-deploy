# CloudMeet 会议媒体验收探针（media-acceptance）

从**客户端侧**对一台已部署的 CloudMeet/Jitsi 实例做只读验收，定位"会议进得去但频繁断掉"类故障。不 SSH、不改服务器、不产数据。

## 背景（2026-11-17 实际案例）

10.1.2.28 实例（aarch64 包 `cloudmeet-1.0.19-rc2-43221549379-1-aarch64`）会议每 60~90 秒强制刷新重进。用本工具链定位：JVB 只下发 Docker 内网候选 `172.18.0.5:10000/udp`（部署时 `target.env` 的 `MEDIA_HOST` 为空 → `JVB_ADVERTISE_IPS=''`），客户端媒体永远建不起来，ICE 重试 3 次后 `conference.iceFailed` 强制刷新。修复：实例 `target.env` 填 `MEDIA_HOST=<可达地址>`，`eval "$(python3 target.py target.env)"` 后重建 jvb 容器。双人实测 ICE connected、180 秒稳定。

## 前提

- Windows 本机，Node.js ≥ 18，`npm i playwright-core`（无需下载浏览器）
- Chromium：自动探测 playwright 缓存（`%LOCALAPPDATA%\ms-playwright\chromium-*`）或本机 Chrome/Edge；也可用 `CHROME_PATH` 指定
- 网络可达目标实例入口（TCP 8443）和媒体端口（UDP 10000）

```bash
cd deploy/tools/media-acceptance
npm init -y && npm i playwright-core
```

## 三个探针（按顺序跑）

| 顺序 | 脚本 | 验证什么 | PASS 标准 |
|---|---|---|---|
| 1 | `probe-candidates.js` | JVB 下发的 ICE 候选地址 | 候选中包含实例入口主机地址；FAIL=只通告容器内网地址（172.18.x 等），查 `MEDIA_HOST`/`JVB_ADVERTISE_IPS` |
| 2 | `probe-media.js` | 双人假设备媒体连通与稳定性 | 两端 `ICE connected`，全程无 `conference.iceFailed`/页面刷新 |
| 3 | `probe-join.js` | `/cm/meeting/<room>` 完整用户路径 | 填昵称点加入后 Jitsi iframe 嵌入且全程不消失 |

## 参数（环境变量）

| 变量 | 默认 | 说明 |
|---|---|---|
| `TARGET` | `https://10.1.2.28:8443` | 实例完整入口（协议://主机:端口） |
| `ROOM` | 随机 | 房间名/号；探针会创建临时房间，不影响既有会议 |
| `DURATION` | 90~120 | 观察时长（秒），媒体探针建议 ≥120 以覆盖 iceFailed 周期 |
| `NICK` | `probe-bot` | join 探针入会昵称 |
| `CHROME_PATH` | 自动探测 | 浏览器可执行文件路径 |

PowerShell 示例：

```powershell
$env:TARGET="https://10.1.2.28:8443"; node probe-candidates.js
$env:TARGET="https://118.193.36.35:8443"; $env:DURATION=180; node probe-media.js
```

退出码：0=PASS，1=FAIL，2=执行错误。

## 典型故障速查

| 现象 | 含义 | 处理 |
|---|---|---|
| 候选只有 `172.x.x.x`/`10.x` 容器地址 | JVB 未配地址通告 | 实例 `target.env` 设 `MEDIA_HOST=<可达IP>`，`eval "$(python3 target.py target.env)"` 后重建 jvb |
| 候选正确但 ICE 仍 failed | UDP 10000 在客户端路径被拦 | 放行安全组/防火墙/VPN 的 UDP；或启用 JVB TCP(4443)/TURN 兜底 |
| join 探针卡在"正在进入会议…" | 昵称必填未填/应用层 API 异常 | 检查 `/mapi` 接口与浏览器控制台 |
| 探针 2 报 STUN/TURN `service-unavailable` | 未配 TURN，无中继兜底 | 内网直连场景可忽略；跨受限网络建议配 coturn |

## 边界

- 探针用虚拟音视频设备，验证的是**信令+媒体链路**；真实摄像头/麦克风/回声等终端体验仍需真实设备验收。
- 探针只读，不修改目标任何配置；创建的临时房间随探针退出自动销毁。
- 本工具不是发布门禁替代品；验收结论需连同真实设备测试一并记录。

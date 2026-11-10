# 服务说明、已知坑与条件补丁

这是选型清单，不是“全部自动应用”清单。每次由用户选择入口、来源、架构和范围后，核对本次版本/Compose再决定；实例地址不属于补丁参数默认值。

## 1. 服务及依赖

| 逻辑服务 | 是什么/依赖 | 典型坑与预防 | 验证 |
|---|---|---|---|
| gateway | 统一入口、TLS，路由业务Web/API和Jitsi；Nginx或Caddy可复用其一 | 端口与已有服务冲突、代理不转WebSocket、路径重写、证书/备案。DNS-01配置须有对应Caddy模块及受限凭据；不能用标准镜像冒充插件版 | 实际公网证书、业务/信令路径，检查代理origin |
| app-web | Vue/Vite业务页面；依赖API和Jitsi external API | VITE为构建期变量、旧hashed资源、错误/cm基础路径、iframe跨域；老WebView不支持新语法。生成物检查及原子发布，保留旧assets | 新JS/CSS摘要、实际iframe同源、WebView专项 |
| api | Spring Boot业务接口、SQLite、主持人JWT和会标 | DB丢失/写入中复制不一致；JWT app_id/secret/sub不匹配；会标目录权限/只读共享。docker-jitsi-meet内部JWT域通常meet.jitsi，不等于公网域名 | health/关键接口、JWT角色、数据挂载和会标访问 |
| jitsi-web | Jitsi会议静态页面与XMPP入口；依赖Prosody/Jicofo/JVB | PUBLIC_URL协议/端口错误；HTTP下硬编码https iframe；前端品牌覆盖被白名单丢弃；custom.css 404 | external API实际iframe、信令会话、品牌和CSS |
| prosody | XMPP登录、MUC房间和角色 | 项目storage属主需匹配镜像uid/gid（现有基线1000）；插件没真正加载；业务JWT不映射房间角色 | 实际运行配置、插件加载、focus/jvb登录和OWNER/PARTICIPANT |
| jicofo | 会议协调、选择JVB | 自动owner把普通成员提升；REST端口冲突；与Prosody凭据/版本不匹配 | 实际auto-owner配置、发现JVB、会议日志 |
| jvb | 多方音视频转发；依赖XMPP及可达媒体路径 | advertise地址为错误内网/代理IP、UDP/NAT单向不通、镜像架构错、历史非官方镜像DTLS不兼容；首次端口冲突可能留坏网络状态 | 镜像平台与版本、实际公网映射、三端JVB媒体/ICE统计 |

Compose名称依方案不同：仓库根 `web` 是业务Web；ARM参考里的 `web` 是Jitsi Web，`app-web` 才是业务Web。先建逻辑服务→实际服务映射，不按名字猜。

依赖准备通常先网络/数据/凭据，继而Prosody、Jicofo/JVB、Jitsi Web、API/业务Web、网关，按实际depends_on和就绪条件调整；Compose启动次序不等于应用已就绪。

## 2. 补丁登记表（每次部署填写）

| ID | 补丁/配置与适用条件 | 来源/目标及持久方式 | 必测与回滚 |
|---|---|---|---|
| P01 | 同源入口：需要iframe DOM访问且当前origin不一致时 | 业务Web当前入口选择代码、构建配置和网关；使用本次origin或已验证same-origin实现，保留原环境配置 | 实际iframe origin、非本环境地址排查；回滚候选配置/产物 |
| P02 | 服务端品牌：当前Jitsi版本不接受相应interface覆盖时 | `deploy/patches/web/custom-interface_config.js` → Jitsi持久Web配置；不要只改容器层 | 运行interface_config及会议视觉；恢复旧持久文件 |
| P03 | CSS注入：需要本项目主题时 | `jitsi-meet-web/src/assets/custom.css`、`deploy/patches/web/custom-head.html`、`deploy/patches/web/nginx-custom/custom-css.conf`配套复制到持久Web配置；核对仓库实际文件 | CSS hash/200、head引用和真实页面；恢复整套旧文件 |
| P04 | JWT主持人角色：使用当前项目主持人方案且镜像未包含时 | `jitsi-meet-cfg/prosody/prosody-plugins-custom/mod_muc_jwt_owner.lua` → Prosody自定义模块持久目录，配置加载muc_jwt_owner；配合Jicofo关闭auto-owner | 实际模块加载、主持人OWNER/普通PARTICIPANT；恢复旧模块与配置，窗口内重建受影响服务 |
| P05 | HTTP external_api：用户批准HTTP测试且该版本硬编码https时 | `deploy/patches/optional-http/external_api.js`，先确认存在、来源及与上游版本相容；挂载到实际serve的`libs/external_api.min.js`，不是根目录同名文件 | HTTP iframe协议、入会；恢复原挂载/官方文件。HTTPS且无需求时不应用 |
| P06 | HTTP信令兼容：HTTP测试且模板会生成错误wss/https时 | 参考部署配置BOSH_RELATIVE=1、ENABLE_XMPP_WEBSOCKET=0；核对当前版本支持，持久配置而非手改运行文件 | 真实BOSH交互；回滚旧信令配置。HTTPS正常WebSocket不照搬 |
| P07 | 客户端HTTP限定例外：明确测试且需要媒体时 | 现有Electron仅配置origin的secure-context例外，Android仅批准主机的明文策略；不能全局关证书校验，新增主机要审核是否支持 | 指定origin媒体可用、其他origin未放宽；恢复配置并重打包（如需要） |
| P08 | 老WebView语法：需支持现有Android WebView时 | 使用现有业务Web构建策略及`check:webview-syntax`，不要只检查源码；依赖输出也需兼容 | 生成JS语法和真机；恢复旧前端候选 |

P04不包含未经验收的host-transfer模块。存储chown、JWT秘密一致、JVB公网映射及端口选取属于条件配置修复，也要列在本次服务计划里，不藏在后台执行。

镜像路线：检查镜像内是否已含P01–P08，不重复注入、不猜文件布局；仅支持验证过的挂载/派生方式。版本变化后旧patch不能自动套用；说明差异并暂停不兼容补丁。记录每项真实摘要/版本，不能伪造校验值。

本批GHCR镜像另读 [镜像清单与运行契约](ghcr-images.md)：仅amd64，ARM64后续单独处理。API内置ENTRYPOINT/JAR，必须清除旧command和宿主JAR；业务Web内置资源/配置，必须移除旧dist/nginx.conf遮盖。gateway对应cloudmeet-caddy，web对应cloudmeet-web，不能以统一仓库前缀拼接旧名称。镜像不包含目标秘密、CA私钥和数据库；外置配置/适用补丁仍需准备。七包公开清单可读不代表组合或媒体验收通过。

## 3. 发布和回滚特有陷阱

- 既有静态发布脚本可能硬编码服务器路径/容器名且没有锁：先核对，串行发布、备份完整文件及非hash变更清单。新环境不直接调用实例脚本。
- 既有API脚本会finally启动容器，但复制失败可能留下坏JAR；容器已启动不等于回滚完成。核对摘要、health和接口。
- 镜像更新保存旧digest/镜像ID，不用可变tag作为唯一回滚证据；SQLite schema变更需明确数据兼容，不能自动覆盖备份后的业务数据。
- 镜像源失败/网络慢不能以不可信镜像代替；离线包需同源、架构和摘要校验。平台/权限不满足报告阻塞，不自动启用模拟或更换路线。
- 源码全栈不能缩成业务Web/API源码加四个官方Jitsi应用镜像。匹配版本的docker-jitsi-meet生命周期模板和generic base可作为运行时输入，但Jitsi Web/Jicofo/JVB/Prosody应用产物必须来自本次已核验源码；保留模板revision、源码commit/归档、构建结果及镜像实际inspect身份。构建输出config摘要、manifest摘要与引擎返回Id可能不同，分别标明，不混称。

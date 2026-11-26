# HTTP 测试专用补丁（默认关闭）

`external_api.js` 为历史 stable-11146-2 测试副本，让 iframe scheme 跟随宿主。只有明确批准 HTTP 测试、确认目标版本仍有该问题后，才挂载至 Jitsi Web `/usr/share/jitsi-meet/libs/external_api.min.js:ro`。

按实况配置 BOSH_RELATIVE=1 和关闭 XMPP WebSocket；客户端明文/安全上下文例外只允许精确目标。普通浏览器 HTTP 媒体限制仍存在。

恢复 HTTPS 时移除挂载并成组审查入口、客户端、BOSH/WS，重建 web 并验证真实信令。不能将该整份 JS 用于未经兼容验证的新版本。

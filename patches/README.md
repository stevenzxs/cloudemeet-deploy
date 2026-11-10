# 持久化补丁说明

本目录是发布所用实际补丁副本，不依赖其他部署目录。源码项目用于维护业务代码；补丁变更须同步本目录并更新发布清单摘要。

| 文件 | 目标 | 生效及验证 |
|---|---|---|
| web/custom-interface_config.js | data/jitsi/web/ | 重启 web，检查运行 interface_config 与视觉 |
| web/custom.css、custom-head.html | data/jitsi/web/ | 配合下述 Nginx 规则；检查 CSS 200、摘要、head 引用 |
| web/nginx-custom/custom-css.conf | data/jitsi/web/nginx-custom/ | 映射 /css/custom.css 和 /head.html 到 /run/web/config |
| prosody/mod_muc_jwt_owner.lua | data/jitsi/prosody/prosody-plugins-custom/ | XMPP_MUC_MODULES=muc_jwt_owner，ENABLE_AUTO_OWNER=false；验证真实角色 |

`start.sh` 复制这些文件，修正公开文件权限。当前参考 Jitsi 组合 stable-11146-2；更换版本先验证加载机制与 API 兼容。当前未启用主持人转移、HTTP iframe 和 HTTP 信令降级补丁。

成套备份及恢复补丁和配置，不修改容器只读层；回滚后重启受影响服务并再次验证。配置存在不是运行验收证据。

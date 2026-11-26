/**
 * docker-jitsi-meet web 容器自定义 interface_config。
 *
 * 背景：stable-11146 起 external API 的 interfaceConfigOverwrite 走 URL 参数白名单，
 * SHOW_JITSI_WATERMARK / APP_NAME / MOBILE_APP_PROMO 等键不在白名单内会被静默丢弃，
 * 前端（jitsi-meet-web JitsiFrame.vue）的覆盖不再生效，必须在服务端下发。
 *
 * 生效机制：web 容器启动时 /etc/s6-overlay/scripts/config 会把
 * /config/custom-interface_config.js 追加到 interface_config.js 末尾（赋值覆盖默认值）。
 *
 * 部署：上传到 ${CONFIG}/web/（云服务器为 /root/.jitsi-meet-cfg/web/）后重启 web 容器。
 */

// 会议中不显示 Jitsi 水印（默认 true，且会链接到 https://jitsi.org）
interfaceConfig.SHOW_JITSI_WATERMARK = false;
interfaceConfig.SHOW_WATERMARK_FOR_GUESTS = false;
interfaceConfig.SHOW_BRAND_WATERMARK = false;
interfaceConfig.JITSI_WATERMARK_LINK = '';

// 产品名与移动端推广（前端覆盖同样被白名单丢弃，需服务端下发）
interfaceConfig.APP_NAME = '云会议';
interfaceConfig.NATIVE_APP_NAME = '云会议';
interfaceConfig.MOBILE_APP_PROMO = false;

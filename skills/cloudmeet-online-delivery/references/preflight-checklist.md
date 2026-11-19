# 标准预检检查表

与同目录上级SKILL一起使用，仅操作索引，不修改知识库/AGENTS规范。

1. 核验知识库/配置库最新main、脏状态、加载SHA；有并发工作不覆盖。
2. 固定origin和任务终点；完整值不再问。delivery-target.py只读派生；域名独立核验同机身份。
3. 查Actions工作流/Run及GHCR镜像权限和身份，不把网络错误当无镜像。
4. 专用版本Runner的隔离与可信执行、仓库变量、持久台账、历史高水位和独立备份恢复证据，缺任何项不先dispatch排队。
5. Android Secrets名称：ANDROID_KEYSTORE_BASE64、ANDROID_KEYSTORE_PROPERTIES_BASE64，最终签名指纹按config/signing-policy.json；Windows Secrets名称：WINDOWS_PFX_BASE64、WINDOWS_PFX_PASSWORD、CERTIFICATES_READ_TOKEN，以及证书库固定提交的windows/public/identity.json。缺项一次性报告，不提供未签名降级。
6. 严格SSH只读核对目标身份/OS/架构、容器/卷/数据/目录、端口/内存/磁盘。首装默认setup.py，既有安装不覆盖。
7. 证书只查身份/期限/SAN/匹配/权限与恢复证据，不输出私钥/密码；保留CA，正确区分安装目标叶证书和CA轮换。
8. 仅预检到此停止；明确执行任务按标准授权连续推进，无需重复确认固定选择。未知凭据/材料、歧义或新授权边界一次报告。

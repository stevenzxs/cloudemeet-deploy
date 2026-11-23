# 标准预检检查表

与同目录上级SKILL一起使用，仅操作索引，不修改知识库/AGENTS规范。

1. 核验知识库/配置库最新main、脏状态、加载SHA；有并发工作不覆盖。
2. 固定origin和任务终点；完整值不再问。delivery-target.py只读派生；域名独立核验同机身份。
3. 查Actions工作流/Run及GHCR镜像权限和身份，不把网络错误当无镜像。
4. 专用版本Runner的隔离与可信执行、仓库变量、持久台账、历史高水位和独立备份恢复证据，缺任何项不先dispatch排队。
5. Android Secrets名称：ANDROID_KEYSTORE_BASE64、ANDROID_KEYSTORE_PROPERTIES_BASE64，最终签名指纹按config/signing-policy.json，缺项拒绝，不用debug替代。Windows按2026-11-20批准取消代码签名：不要求PFX/SignTool/私有证书库检出，交付明确unsigned及未知发布者/SmartScreen风险，不写验签通过。两端HTTPS CA信任/入口/版本/ABI/摘要门禁保留。
6. 严格SSH只读核对目标身份/OS/架构、容器/卷/数据/目录、端口/内存/磁盘。首装默认setup.py，既有安装不覆盖。
7. 证书只查身份/期限/SAN/匹配/权限与恢复证据，不输出私钥/密码；保留CA，正确区分安装目标叶证书和CA轮换。
8. 仅预检到此停止；明确执行任务按标准授权连续推进，无需重复确认固定选择。未知凭据/材料、歧义或新授权边界一次报告。
9. 联合发布须等待七服务/双客户端成功，核对同Run/attempt/配置SHA/分配/origin/公开CA；GHCR七digest和持久GitHub Release齐备才称发布完整，draft上传失败不公开。
10. 发布后只补问first/upgrade、server及匹配客户端的origin缺项；升级核实实际root/project/外部target.env。配置/补丁变化拒绝image-only自动升级，不清理重装。离线附加节点须明确批准、固定digest导出、目标只load，不编译/占新rN。

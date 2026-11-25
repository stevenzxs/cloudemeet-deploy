# CloudMeet 双证书模式实施计划

目标：保留 private-ca，新增 caddy-public-acme；每批固定一种模式，不改联合rN/签名/digest/数据保留，禁止自动回退。本任务不构建发布、不连接目标、不换证或重启。

1. 配置契约：client.env新增TLS_MODE，私有模式要求公开根，公共模式仅HTTPS DNS/443且禁止CLIENT_CA_FILE；历史包未声明模式按原私有证书处理，新材料写入模式。
2. 客户端：Electron使用系统公共信任；Android生成指定主机system trust anchor，最终资源检查同样验证；私有CA行为不变。
3. 材料与联合发布：candidate/客户端报告绑定模式、origin和可空CA摘要；不以空CA隐式猜模式；包内INSTALL区分证书先决条件。
4. 目标公共核心：同一certificate.py支持模式预检、Caddy公网DNS站点自动HTTPS、只用TLS-ALPN-01/443；不创建私有回退证书，保留内部TLS及Caddy持久卷。setup/deploy不要求公共模式叶证书包，默认公共信任验证。公共模式只允许registry在线首装，离线隔离目标拒绝；同模式升级保留ACME状态、模式切换拒绝普通升级。
5. 规范/知识库/Skill/职责/输入摘要同步；定向测试先失败再修复，校验现有私有分支；不将mock或静态配置当真实签发续期验收。

文件：config/client.env、build-tools/clients/{core,ca-config,build-clients,verify-package}.cjs及tests；build-tools/{online-material,joint-release,setup}.py；build-tools/offline-runtime/{certificate,deploy,image_transport,online_update}.py；相关tests、AGENTS.md、Skill、inputs.sha256与知识库规范/台账。

验证：node --test build-tools/clients/tests/*.test.cjs；Linux/WSL python3 -B -m unittest discover -s build-tools/tests -p 'test_*.py'；布局/治理/摘要/差异检查。若现有基线失败分开报告，不改无关功能。正式Actions、最终产品、目标公网ACME签发/续期、客户端真机均待后续授权验收。

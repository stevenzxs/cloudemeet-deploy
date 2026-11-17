# 离线 IP 证书维护工具

## 唯一维护源与在线签发授权（2026-11-17）

`deploy/cert/` 是证书工具代码的唯一维护源，随配置仓库版本管理；不在
cloudmeet-certificates 或150另维护一份可编辑源码。150执行前获取配置库固定提交，
记录工具版本。用户已允许150.158.83.70作为在线签发机持有专用CA私钥；这是下文
“仅离线签发”的明确目标例外，不授权本次生成、迁移或替换任何证书。

150上的专用CA、密码、签发输出和敏感归档存放于仓库及Hermes普通工作区之外的
受限运行目录。CA私钥不得提交Git、进入Actions/镜像或分发到118；仅服务器叶证书、
叶私钥、公开根、证书元数据及摘要可组成目标专属敏感包，经严格SSH传到目标侧。
代码/公共配置包与敏感证书包分开；部署脚本引用文件路径，不嵌入私钥内容。
生成前复用有效证书和既有CA，续期沿用CA；118现有Caddy证书卷默认保留，
迁移CA或换证必须另获批准。部署前检查链、SAN、期限及密钥匹配，保留回滚材料。

本地历史材料不属于工具源码：private-ca/、cert-pwd.txt及两个tar.gz/摘要继续保留且
不纳入Git。2026-11-17整理删除的解压目录cert/、update-47-001/已逐文件核对为
对应原始tar.gz的相同字节；update-47-001.zip仅含其中部分文件，根ca.crt有相同
副本保存在private-ca/及归档。保留归档不表示其适用于118或已部署。

脚本、测试及本文在根目录维护；归档内的代码仅为不可变历史快照，不回写同步。

## 固定标签 JSON 实例（优先于下文旧 Caddyfile 操作）

外部标签固定 `cert`，内部标签固定 `cert-inner`。不能仅改证书文件名：Caddyfile 的
`tls CERT KEY` 会生成顺序相关的 cert0/cert1；旧标签可能在热加载缓存中累加。
已迁移实例禁止运行旧 replace-cert.sh/rollback-cert.sh 或 reload 旧 Caddyfile。

本地工具只生成候选，不连接服务器：

```sh
python cert-tool.py fixed-json --input reviewed-runtime.json --output candidate.json --certificate-directory /config/cloudmeet-cert/BATCH
```

输入应为管理员审核的当前原生配置或 caddy adapt 输出，必须正好有外部文件证书和
`/host-control/gateway.crt` 内部证书，监听为 :443/:9443 及可选 :80。
输出拒绝覆盖；保留路由、端口、内部密钥路径，全部 TLS 策略显式限定固定标签。
此命令不支持自动签发的 tls internal 基线；不代表服务端打包链路已迁移。

首次迁移必须备份配置、校验候选并显式审批运行变更。Compose gateway 的 command
与实际容器启动参数均须为 `run --config /config/cloudmeet-fixed-tags-BATCH.json`。
只改 Compose 再 reload 不会改变既有容器的启动命令，直接 restart 仍会回到旧入口；
需另行批准并执行限定 gateway 重建后验证。不得把未重建实例声称重启持久化完成。

后续外部换证使用新生成的敏感更新包，上传与执行仍需授权：

```sh
bash replace-fixed-cert.sh CONTAINER /config/cloudmeet-fixed-tags-BATCH.json ACCESS_IP --apply
```

脚本拒绝启动参数不匹配的容器；保留内部引用，只替换外部证书路径并 reload 完整 JSON。
保留卷内配置备份和旧证书，不清 CA 卷、不重启其他服务。原生 JSON 回滚应先校验备份，
恢复同一 active JSON 文件并 reload，不得使用旧 Caddyfile 回滚脚本。
换证后连续严格验证无 SNI/SNI 连接及新叶证书指纹、内部 TLS、外部内部路径404与
Electron 实际首页；标签稳定不等于旧叶证书一定已从缓存删除。

本目录只维护工具，不预置共享CA或虚构已签发证书；具体证书生成在用户指定目录。
只适配当前模板：Caddyfile有两处独立的`tls internal`，gateway将实际宿主
Caddyfile挂载至`/etc/caddy/Caddyfile`，并持久化可写`/config`。
其他实例布局、非root容器或已使用自定义证书的配置须先审核，不自动套用。
不连接服务器、不安装依赖、不删除数据/CA卷、不改端口或业务路由。

## 1. 在管理员可信机器生成（Python3、OpenSSL >=1.1.1）

```sh
# 首次创建独立CA，交互输入CA私钥密码；不要放到服务器更新包内。
python3 deploy/cert/cert-tool.py init-ca --directory /安全离线位置/cloudmeet-ca
# IP按客户端实际访问地址填写，可同时包含内网/外网IPv4；不含端口。
python3 deploy/cert/cert-tool.py issue --ca-directory /安全离线位置/cloudmeet-ca --ips 47.96.221.94,192.168.1.10 --output /安全位置/cert-update-001 --days 365
```

路径为示例，必须换成受保护的真实目录。Windows可以用已安装的Python/OpenSSL
运行同一工具；Windows文件ACL须另行核对，umask不替代ACL。
CA私钥加密、保留在离线签发机；服务器叶私钥不加密以便Caddy无人值守读取，
更新包因此是敏感材料，不上传Git/公开artifact/客户端。每次新建输出目录，拒绝覆盖。
签发完成验证链和所有IP，生成server.crt/server.key/ca.crt、脚本和SHA256SUMS。
每批可换IP，映射端口变化无需换证书；换IP必须使新IP出现在SAN中。
续期沿用同一CA重新issue到新目录；叶证书不能长于CA剩余有效期，工具验证不通过即拒绝使用。

## 2. 人工上传、检查并替换

先从可信渠道核对SHA256SUMS本身摘要，限制更新包目录及私钥权限。
先盘点实例并做好数据/配置备份，获得维护授权后，管理员手动执行：

```sh
cd /上传的/cert-update-001
sha256sum -c SHA256SUMS
bash replace-cert.sh 实际gateway容器名 /实际实例/Caddyfile 47.96.221.94 --apply
```

旧版Windows生成的SHA256SUMS可能为CRLF，Linux会将行尾CR识别为文件名字符。
若出现`ca.crt`后带`$'\r'`，仅转换清单：`sed -i 's/\r$//' SHA256SUMS`，
然后重新执行`sha256sum -c SHA256SUMS`。不转换证书/脚本内容，不重新生成摘要掩盖不匹配。
新生成器固定写LF；已有更新包及历史清单不会被工具自动修改。

HOST_CADDYFILE必须是实际bind挂载源，可能位于实例根，也可能位于config/，
脚本不会猜容器或自动重建服务。检查证书有效期至少剩一天、IP匹配、密钥配对，
再写入已有持久化/config下的新版本目录、校验候选配置、备份原Caddyfile并reload。
仅将两处tls internal改成文件路径；原始路由、Host和端口配置不变。
失败保留诊断材料并尝试恢复原配置；必须人工检查服务状态，不宣称绝对原子或零中断。
不自动删除旧证书目录，以便回滚。下次续期可直接对本工具管理的两处TLS路径再次替换，
不必回到旧证书；其他自定义TLS配置会拒绝，须单独审核。

## 3. 回滚

### 旧Caddyfile实例换证后重启及严格验证

新签发的更新包自动包含 `restart-verify-gateway.sh` 并纳入 `SHA256SUMS`。
仅在允许短暂中断的维护窗口，由管理员显式执行：

```sh
bash restart-verify-gateway.sh 实际gateway容器名 https://实际访问IP:8443/cm/desktop/ --apply
```

脚本先校验当前Caddyfile再仅重启指定gateway，使用同目录ca.crt严格校验HTTPS及2xx响应。
不执行换证或首次安装，不适用固定JSON启动实例。旧更新包不自动修改或重新签发。

```sh
bash rollback-cert.sh 实际gateway容器名 /实际实例/Caddyfile /脚本输出的证书前备份路径 --apply
```

备份路径必须来自该实例。脚本校验配置并保留回滚前副本，reload失败尝试恢复。
不删除已上传材料或CA卷。执行结果只证明配置命令完成，不证明远程TLS/媒体通过。

## 4. 客户端

只向Electron/Android分发公开ca.crt，绝不分发server.key或ca.key。
客户端仍需实现限定入口的CA信任；本工具不自动更新客户端。
不要pin会更换的叶证书。CA过期/轮换需另行规划客户端新旧CA过渡。
首次生成/替换未经实机验证；先人工核对证书再执行，不能以单元测试代替安装验收。

1. 创建 CA（首次执行一次）
python ./cert-tool.py init-ca --directory "D:/code/jitsi/deploy/cert/private-ca"
按 OpenSSL 提示设置并确认 CA 私钥密码。

2. 生成 IP 证书和更新脚本
python cert-tool.py issue --ca-directory "D:/code/jitsi/deploy/cert/private-ca" --ips 47.96.221.94 --output "D:/code/jitsi/deploy/cert/update-47-001" --days 365

3. 把生成的整个更新目录上传服务器，例如 update-47-002/。其中需要有 server.crt、server.key、ca.crt、脚本及 SHA256SUMS。
先不要猜容器名和文件路径。 可用以下命令确认：
docker ps --format '{{.Names}}\t{{.Image}}'
docker inspect 实际网关容器名 --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'


docker inspect cloudmeet-1019-rc1-43157641959-1-gateway-1 --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'

进入上传目录，执行：
sed -i 's/\r$//' SHA256SUMS
sha256sum -c SHA256SUMS

bash replace-cert.sh cloudmeet-1019-rc1-43197640865-1-gateway-1  /opt/zihuishuzi/cloudmeet-1.0.19-rc2-43221549379-1-aarch64/Caddyfile 47.96.221.94 --apply

4. 配置校验通过后，仅重启 gateway
docker exec cloudmeet-1019-rc2-43221549379-1-gateway-1 \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
&& docker restart cloudmeet-1019-rc2-43221549379-1-gateway-1

5. 严格验证证书和页面响应
curl --noproxy '*' --cacert ./ca.crt \
  -I --max-time 15 https://192.168.2.28:8443/cm/desktop/


## 公网IP证书与无SNI兼容

issue命令现在始终同时签入指定的IPv4 SAN和`DNS:cloudmeet.internal`，后者匹配Caddy默认TLS身份，不改变实际客户端入口，也不要求DNS解析。命令参数不变，使用原CA重新签发叶证书即可；不要重新init-ca，不将CA私钥上传服务器。已有输出目录拒绝覆盖，请选择新的--output目录。工具分别验证IP与cloudmeet.internal身份；部署后仍需核对无SNI公网握手及内部gateway:9443选证。
# issue 同时输出 tar.gz

`cert-tool.py issue --ca-directory <离线CA目录> --ips <IPv4> --output update-example`
保留 `update-example/`，同时生成 `update-example.tar.gz` 和
`update-example.tar.gz.sha256`。已存在的目录、压缩包或摘要文件不会覆盖。
归档保留顶层目录，包含包内 SHA256SUMS；生成后重新读取成员并核对内容。
归档脚本权限0755、服务器私钥0600、顶层目录0700。
压缩包包含服务器私钥，必须安全传输；不包含CA私钥，init-ca不生成归档。
在Linux上传后先执行 `sha256sum -c update-example.tar.gz.sha256`，再解压，
进入目录执行 `sha256sum -c SHA256SUMS`；换证仍按对应实例及原有脚本前提人工执行。
此功能不修改已有更新包，不自动连接服务器或换证。

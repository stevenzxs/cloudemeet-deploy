# 当前执行记录

## 2026-11-11 Actions打包脚本收敛

- 用户已要求“按建议优化打包脚本”；本轮终点为脚本修改及无Docker辅助回归，不自动提交/推送/调度Actions。
- 已确认：七服务每发布批次完整源码编译、统一版本及run/attempt，不用旧应用镜像补缺；后续发布仅使用已验包内镜像，不重编。
- 保留origin `https://47.110.84.166:8443`、HTTP重定向8080、媒体UDP10000及JWT/品牌补丁。目标由用户手动安装，当前宿主前提未知。
- 新编排：`build-tools/package.sh`；手动工作流维护源`build-tools/build-package.yml`；Dockerfile/源码锁为数据，安装核心统一在offline-runtime。
- 当前七源码HEAD与sources.json一致，七源码目录git status均为空。未更改业务源码/锁文件。
- 补充实际Docker-save归档config/标签/平台/镜像ID检查；不加载镜像、不启动产品容器。最终归档重新读取成员及摘要。
- 安装器接纳完整PACKAGED材料契约，不伪造READY证据；携带官方校验的Compose，明确不含Docker引擎/宿主OS。
- 旧workflow改为仅手动诊断；去除尚未推送的ISO下载/TCG启动步骤。不触及历史包、现有服务器、数据或CA卷。
- build-tools-old为既有用户整理结果，保持原样；旧历史执行证据不迁入本记录、不改字节。
- 状态：继续整批收尾，不把已知实现缺口交回用户；实际原生编译、组包、下载交付均未执行。目标安装、TLS/客户端/媒体未验证；本记录不声称已有完整交付。
- 辅助回归：WSL仅执行无Docker Python单元测试，38/38通过；bash -n通过；CI探测回归3/3通过。旧Windows回归曾因Linux路径/geteuid与过期mock失败，已在新测试副本适配，不改历史工具。
- 已修当前layout登记移除失效工具路径，登记统一入口及initialize；恢复当前服务端治理回归，不搬回旧工具或客户端版本状态。
- 已补配置生成与最终归档检查的实际Python执行回归（微型合成数据，不构建服务器包），覆盖七归档、JWT/补丁、端口、来源与归档摘要；不使用Docker。
- 已补业务Web same-origin构建参数，保留118工作区env；修正多模块Maven跳过测试参数，保留test-jar编译依赖；包内verify-only增加实际镜像归档验证。
- 新workflow经actionlint v1.7.12检查通过；保留同run/attempt artifact ID/digest来源记录。后续最终检查结果以实际输出为准。
- 最终复核：当前单元回归41/41、治理3/3、旧诊断探测回归3/3通过；layout、bash -n、actionlint及CI git diff --check均通过。34项受控输入源/CI字节一致，摘要同步后重核。
- 本轮脚本收尾已完成，未执行git提交/推送/Actions调度，没有新服务器包，不能把本轮辅助验证当作真实编译成功；真实原生构建结果由后续正常workflow运行给出，不新增安装测试门槛。

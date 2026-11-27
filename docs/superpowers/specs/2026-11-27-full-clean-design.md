# full-clean 设计：CloudMeet 实例完整清除技能

日期：2026-11-27
状态：待批准

## 意图

给定服务器上正在运行的 CloudMeet 实例需要彻底清除（服务、数据、证书），为可能的重新安装做准备。技能完全自包含（`skills/full-clean/`），不复用其它目录工具。

## Goals

- SSH 远程驱动：从操作机通过系统 OpenSSH 对目标服务器做只读盘点，确认后执行清除；agent 不直连除外均需主机/用户/密钥。
- 清除范围：compose project 全部容器、该项目具名卷（caddy_data/caddy_config）、`cloudmeet/*` 镜像、实例根目录整体（含 `.env` 秘密、`data/`、`host-control` 证书）。
- 保留：包外 target.env（重装复用）、Docker Engine 本身、一切非 CloudMeet 资源。
- jitsi-mgr 外置 PostgreSQL：按实例配置的 JDBC URL 定位数据库，对该 URL 指定的**专用库**执行 `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`；`psql` 不可用或库名不含 `jitsi` 字样时停止并报告（防止误清共享库）。
- 不做任何备份（用户明确选择）。
- 多实例并存、标记文件缺失、主机指纹不匹配、目标根是 `/`、`/root`、`/home` 等危险路径时拒绝。

## Non-goals

- 不安装/重装 CloudMeet；不验证重装。
- 不碰客户端（Windows/Android）上的 CA 信任。
- 不做全局 prune、不删无关 Docker 资源、不轮转秘密。

## Anti-goals

- 未经只读盘点直接清除；模糊识别实例（凭目录名猜）。
- 任何未列在盘点清单里的删除动作。

## 安全与流程

1. `--inventory`（默认）：SSH 只读收集——主机指纹（首次需 `--accept-fingerprint`）、docker/compose 可用性、按 compose project label 归组的容器、`com.docker.compose.project` 标签卷、`cloudmeet/*` 镜像、实例根标记文件（candidate.json/jitsi-base.yaml/.env/data）、jitsi-mgr DB URL。输出清单 JSON。
2. 人工核对清单后 `--apply`：按清单逐项删除（compose down 失败则按 label 逐个 `docker rm -f`；`docker volume rm` 仅带项目标签的卷；`docker rmi` 仅 `cloudmeet/*`；`rm -rf` 仅实例根且过标记检查；postgres schema 按上述规则）。
3. 结束后验证零残留并输出 `READY_FOR_REINSTALL`（不代表已重装）。

## 文件

```
skills/full-clean/
  SKILL.md            # 中文：范围/授权/阶段/必须停止情形
  tools/clean.py      # 自包含 SSH 驱动（runner 可注入，测试无真实 SSH）
  tests/test_clean.py
```

## 必须停止并报告

- SSH/指纹失败；实例标记缺失或多实例歧义。
- 清单含非 CloudMeet 容器/卷/镜像会被触碰的迹象。
- postgres 专用库判定不成立或 psql 不可用。
- 任何清单外资源需要删除。

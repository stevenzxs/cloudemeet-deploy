---
name: cloudmeet-full-clean
description: Use when completely wiping a running CloudMeet instance from a Linux server (all service containers, compose volumes, cloudmeet images, instance data, secrets and certificates) to prepare for a clean reinstall. Triggers on "完整清除实例/清除云会议实例/卸载 CloudMeet/清理服务器实例/full clean/删除实例重装". Every run requires explicit host, instance root and read-only inventory confirmation before any deletion. Not for backup, reinstall, upgrades, or build/release.
---

# Skill: full-clean

# CloudMeet 实例完整清除（为重装做准备）

本技能用于把指定服务器上正在运行的 CloudMeet 实例**彻底清除**：全部服务容器、项目卷、镜像、实例数据、秘密与证书。它是操作步骤，不构成额外授权；每次清除都必须由用户明确给出主机与实例路径并确认盘点清单。清除不等于重装，重装是另一个独立动作。

设计依据：`docs/superpowers/specs/2026-11-27-full-clean-design.md`。

## 范围

- **清除**：compose project 全部容器；带 `com.docker.compose.project` 标签的卷（caddy_data/caddy_config，ACME 证书所在）；`cloudmeet/*` 镜像；实例根目录整体（含 `.env` 秘密、`data/`、`host-control` CA 与 gateway 证书）；jitsi-mgr 外置 PostgreSQL 专用库的 schema（仅当 JDBC URL 为 postgres 且库名含 `jitsi`，按实例凭据执行）。
- **保留**：包外 target.env（重装复用）、Docker Engine、一切非 CloudMeet 资源。
- **不做**：备份（用户明确选择不备份）、全局 prune、客户端 CA 信任处理、重装或其验证。

## 执行（两阶段，缺一不可）

工具：`skills/full-clean/tools/clean.py`（自包含；需 Python 3）。**默认本地模式**：把脚本上传到目标服务器后在该服务器直接运行，无 SSH 客户端、主机指纹与密钥环节；`--remote` 为旧 SSH 远程模式（需 `--host`/`--identity-file`/`--accept-fingerprint`）。

1. **只读盘点**（必做第一步）：

   ```bash
   # 在目标服务器上执行
   python3 -B clean.py --instance-root /绝对/路径/实例根
   ```

   输出 JSON 清单：主机、compose project、容器、卷、镜像、postgres 目标库。实例标记同时兼容旧格式（candidate.json/jitsi-base.yaml）与新格式（compose.yaml/images.json，server-build-deploy 安装的实例）。

2. **人工核对清单**：确认清单里的每一项都属于要清的实例；出现陌生容器/卷/镜像或多实例迹象时停止。

3. **执行清除**：同一命令加 `--apply`。按清单顺序执行（容器→卷→网络→镜像→实例根→postgres schema），结束后自动验证零残留并输出 `READY_FOR_REINSTALL`。

## 必须停止并报告的情形

- `--remote` 模式下 SSH 不通、指纹缺失或不匹配。
- 实例标记缺失（candidate.json/jitsi-base.yaml/compose.yaml/images.json 与 data 不可同时验证）、多 CloudMeet compose project 并存、实例根为危险路径。
- jitsi-mgr 为非 postgres 之外的未知 URL 形态、库名不含 `jitsi`（疑似共享库）、目标上 `psql` 不可用。
- 清除后验证发现任何残留。
- 请求超出清除范围（安装、备份、客户端操作、其它实例）。

停止时报告：已完成的阶段、精确失败项、远端当前状态、仍未执行的阶段；不自行扩大清除范围。

## 清理后的重装注意事项

- CA 与 JWKS 密钥已清除：重装后生成全新 CA，客户端必须重新分发/信任新 CA 根，旧信任记录无效。
- `.env` 秘密已清除：重装会生成全新秘密，旧 token/会话全部失效。
- ACME 缓存（caddy_data）已清除：首次重装会重新向公共 CA 申请证书，受速率限制影响需留意。

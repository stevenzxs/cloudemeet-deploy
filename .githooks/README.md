# Git Hooks 安装与使用

## 自动检查构建材料校验和

本仓库提供 Git pre-commit hook，在提交时自动检查：修改构建文件时是否同时更新了 `build-tools/inputs.sha256`。

## 安装方法

### 一次性安装（推荐）

```bash
# 在仓库根目录执行
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
chmod +x .githooks/update-inputs-sha256.sh
```

### 手动复制安装

```bash
cp .githooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
chmod +x .githooks/update-inputs-sha256.sh
```

## Hook 功能

### pre-commit

**触发条件**：提交包含以下目录的文件修改时
- `build-tools/`
- `config/`
- `.github/workflows/`
- `skills/`

**检查内容**：
1. 是否同时修改了 `build-tools/inputs.sha256`
2. `inputs.sha256` 中的哈希是否与实际文件一致

**失败处理**：
- 如果检测到构建文件修改但 `inputs.sha256` 未更新，提交将被阻止
- 显示需要更新的文件列表
- 提供修复建议

**跳过检查**（不推荐）：
```bash
git commit --no-verify
```

## 辅助脚本

### update-inputs-sha256.sh

自动重新生成 `build-tools/inputs.sha256` 文件。

**使用方法**：
```bash
bash .githooks/update-inputs-sha256.sh
```

**执行步骤**：
1. 读取现有文件列表
2. 重新计算所有文件的 SHA256
3. 计算 `inputs.sha256` 自身的哈希
4. 更新文件并显示差异

**后续操作**：
```bash
git add build-tools/inputs.sha256
git commit
```

## 验证安装

检查 hook 是否生效：

```bash
# 查看当前 hooks 路径
git config core.hooksPath

# 应该输出：.githooks

# 或检查符号链接
ls -l .git/hooks/pre-commit
```

## 工作流示例

### 场景：修改构建脚本

```bash
# 1. 修改构建文件
vim build-tools/package.sh

# 2. 更新 inputs.sha256
bash .githooks/update-inputs-sha256.sh

# 3. 检查差异
git diff build-tools/inputs.sha256

# 4. 一起提交
git add build-tools/package.sh build-tools/inputs.sha256
git commit -m "feat: update package script"

# ✓ pre-commit hook 自动验证通过
```

### 场景：忘记更新 inputs.sha256

```bash
# 1. 修改构建文件
vim build-tools/setup.py

# 2. 尝试提交（忘记更新 inputs.sha256）
git add build-tools/setup.py
git commit -m "fix: update setup"

# ❌ pre-commit hook 阻止提交
# 错误：检测到构建文件修改，但 build-tools/inputs.sha256 未更新
#
# 修改的构建文件：
#   - build-tools/setup.py
#
# 请执行以下操作：
#   1. 重新计算修改文件的哈希并更新 inputs.sha256
#   2. 或运行: bash .githooks/update-inputs-sha256.sh
#   3. git add build-tools/inputs.sha256

# 3. 按提示修复
bash .githooks/update-inputs-sha256.sh
git add build-tools/inputs.sha256
git commit -m "fix: update setup"

# ✓ 提交成功
```

## 卸载

```bash
# 恢复到默认 hooks 路径
git config --unset core.hooksPath

# 或删除 hook 文件
rm .git/hooks/pre-commit
```

## 故障排查

### Hook 未执行

**检查权限**：
```bash
ls -l .githooks/pre-commit
# 应该包含 x (可执行) 权限

# 如果没有，添加权限
chmod +x .githooks/pre-commit
```

**检查路径配置**：
```bash
git config core.hooksPath
# 应该输出 .githooks

# 重新设置
git config core.hooksPath .githooks
```

### 在 Windows 上执行

如果使用 Git Bash 或 WSL，hook 应该正常工作。

如果使用 PowerShell，需要确保：
1. Git 配置使用 bash 执行 hooks
2. 或将 hook 改写为 PowerShell 脚本

### 哈希验证失败

```bash
# 重新生成所有哈希
bash .githooks/update-inputs-sha256.sh

# 检查文件完整性
sha256sum -c build-tools/inputs.sha256
```

## 维护

### 添加新的校验文件

如果新增了需要校验的文件类型，修改 `pre-commit` 中的正则表达式：

```bash
# 当前匹配
grep -E '^(build-tools/|config/|\.github/workflows/|skills/)'

# 添加新目录，例如 patches/
grep -E '^(build-tools/|config/|\.github/workflows/|skills/|patches/)'
```

### 团队协作

建议在 `README.md` 中提醒团队成员安装 hooks：

```markdown
## 开发环境设置

克隆仓库后，请安装 Git hooks：

\`\`\`bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
chmod +x .githooks/update-inputs-sha256.sh
\`\`\`
```

## 参考

- 知识库规范：`D:/knowledgebase/standards/project-delivery.md`
- 失败教训：2026-11-25 双TLS模式提交事件（commit `865e1e2`）
- Actions 失败：Run 45574142788

#!/usr/bin/env bash
# 自动重新生成 build-tools/inputs.sha256
# 用于更新构建材料校验和

set -e

cd "$(git rev-parse --show-toplevel)"

echo "正在重新生成 build-tools/inputs.sha256..."

# 临时文件
TEMP_SHA256=$(mktemp)

# 读取现有文件列表（排除 inputs.sha256 自身和 .new）
if [ -f build-tools/inputs.sha256 ]; then
    grep -v 'inputs\.sha256' build-tools/inputs.sha256 | awk '{print $2}' > "$TEMP_SHA256.files" || true
else
    echo "错误：build-tools/inputs.sha256 不存在"
    exit 1
fi

# 计算所有文件的新哈希
> "$TEMP_SHA256"
while IFS= read -r file; do
    if [ -f "$file" ]; then
        sha256sum "$file" >> "$TEMP_SHA256"
    else
        echo "⚠ 警告：文件不存在，跳过：$file"
    fi
done < "$TEMP_SHA256.files"

# 对结果排序（保持稳定顺序）
sort -k2 "$TEMP_SHA256" > "$TEMP_SHA256.sorted"

# 计算 inputs.sha256 自身的哈希并添加
SELF_HASH=$(sha256sum "$TEMP_SHA256.sorted" | awk '{print $1}')
echo "$SELF_HASH  build-tools/inputs.sha256" >> "$TEMP_SHA256.sorted"

# 再次排序（包含自身）
sort -k2 "$TEMP_SHA256.sorted" > build-tools/inputs.sha256

# 清理临时文件
rm -f "$TEMP_SHA256" "$TEMP_SHA256.files" "$TEMP_SHA256.sorted"

echo "✓ build-tools/inputs.sha256 已更新"
echo ""
echo "请检查差异："
git diff build-tools/inputs.sha256 | head -50
echo ""
echo "如无问题，请执行："
echo "  git add build-tools/inputs.sha256"
echo "  git commit"

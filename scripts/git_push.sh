#!/bin/bash

# MOSSAI Git 提交推送脚本
# 使用方法: ./scripts/git_push.sh

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== MOSSAI Git 提交推送脚本 ===${NC}\n"

# 检查是否在git仓库中
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}错误: 当前目录不是一个Git仓库${NC}"
    exit 1
fi

# 获取当前分支
CURRENT_BRANCH=$(git branch --show-current)
echo -e "${CYAN}当前分支: ${YELLOW}$CURRENT_BRANCH${NC}\n"

# Step 1: 显示当前状态
echo -e "${GREEN}步骤 1/4: 检查文件状态${NC}"
git status --short

# Step 2: git add .
echo -e "\n${GREEN}步骤 2/4: 添加所有更改${NC}"
git add .

# 检查是否有更改
if git diff --staged --quiet; then
    echo -e "${YELLOW}没有需要提交的更改${NC}"
    echo -e "${CYAN}提示: 所有文件都已是最新状态${NC}"
    exit 0
fi

echo -e "${GREEN}已暂存的更改:${NC}"
# 禁用分页器，避免卡住
git --no-pager diff --staged --stat

# Step 3: git commit
echo -e "\n${GREEN}步骤 3/4: 提交更改${NC}"
echo -n "请输入提交信息: "
read commit_message

if [ -z "$commit_message" ]; then
    echo -e "${RED}错误: 提交信息不能为空${NC}"
    exit 1
fi

git commit -m "$commit_message"
echo -e "${GREEN}✓ 提交成功${NC}"

# 显示最近的提交
echo -e "\n${CYAN}最近的提交:${NC}"
git log --oneline -1

# Step 4: git push
echo -e "\n${GREEN}步骤 4/4: 推送到远程仓库${NC}"
echo -e "${YELLOW}正在推送到 origin/$CURRENT_BRANCH...${NC}"

git push origin "$CURRENT_BRANCH"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 推送成功${NC}"
else
    echo -e "${RED}推送失败${NC}"
    echo -e "${YELLOW}提示: 如果遇到分支分歧，请运行以下命令解决：${NC}"
    echo -e "${YELLOW}  git pull --rebase${NC}"
    echo -e "${YELLOW}  git push${NC}"
    exit 1
fi

echo -e "\n${GREEN}=== 所有操作完成！===${NC}"
echo -e "${GREEN}✓ 更改已提交并推送到远程${NC}"
echo -e "${GREEN}✓ 分支: $CURRENT_BRANCH${NC}"

# 显示远程仓库状态
echo -e "\n${CYAN}远程仓库状态:${NC}"
git log --oneline origin/$CURRENT_BRANCH -3 2>/dev/null || echo -e "${YELLOW}无法获取远程日志${NC}"


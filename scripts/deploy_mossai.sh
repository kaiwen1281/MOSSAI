#!/bin/bash

# MOSSAI 部署脚本
# 配置参数
APP_DIR="/srv/moss-ai/MOSSAI"
SERVICE_NAME="moss-ai.service"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== MOSSAI 部署脚本 ===${NC}\n"

# 检查目录是否存在
if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}错误: 应用目录 $APP_DIR 不存在!${NC}"
    exit 1
fi

# 进入应用目录
echo -e "${YELLOW}进入应用目录: $APP_DIR${NC}"
cd "$APP_DIR" || {
    echo -e "${RED}错误: 无法进入目录 $APP_DIR${NC}"
    exit 1
}

# 检测主分支名称
echo -e "\n${GREEN}检测主分支名称...${NC}"
CURRENT_BRANCH=$(git branch --show-current)
echo -e "${YELLOW}当前分支: $CURRENT_BRANCH${NC}"

# 拉取最新代码
echo -e "\n${GREEN}从Git仓库拉取最新代码...${NC}"
git pull origin "$CURRENT_BRANCH"

# 检查git pull是否成功
if [ $? -ne 0 ]; then
    echo -e "${RED}错误: git pull 操作失败!${NC}"
    echo -e "${YELLOW}提示: 如果遇到分支分歧，请运行以下命令解决：${NC}"
    echo -e "${YELLOW}  git config pull.rebase false${NC}"
    echo -e "${YELLOW}  git pull${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 代码拉取成功${NC}"

# 重启服务
echo -e "\n${GREEN}重启服务: $SERVICE_NAME...${NC}"
sudo systemctl restart "$SERVICE_NAME"

# 检查服务是否重启成功
if [ $? -ne 0 ]; then
    echo -e "${RED}错误: 服务 $SERVICE_NAME 重启失败!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ 服务重启成功${NC}"

# 等待服务启动
echo -e "\n${YELLOW}等待服务启动 (3秒)...${NC}"
sleep 3

# 检查服务状态
echo -e "\n${GREEN}检查服务状态...${NC}"
sudo systemctl status "$SERVICE_NAME" --no-pager | head -n 15

echo -e "\n${GREEN}=== 部署完成！===${NC}"
echo -e "${GREEN}✓ 代码已更新${NC}"
echo -e "${GREEN}✓ 服务已重启${NC}"
exit 0


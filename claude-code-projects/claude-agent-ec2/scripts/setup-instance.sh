#!/bin/bash
# Interactive setup script for non-CloudFormation deploys.
# Run this on a fresh Amazon Linux 2023 EC2 instance via SSM.
#
# Usage: sudo bash setup-instance.sh

set -euo pipefail

echo "=== Discord Bot (Bedrock) — Interactive Setup ==="
echo ""

# Prompt for required values
read -rp "Discord bot token: " DISCORD_TOKEN
read -rp "Discord channel ID: " DISCORD_CHANNEL_ID
read -rp "Bedrock model [us.anthropic.claude-sonnet-4-20250514]: " BEDROCK_MODEL
BEDROCK_MODEL="${BEDROCK_MODEL:-us.anthropic.claude-sonnet-4-20250514}"
read -rp "AWS region [us-east-1]: " AWS_REGION
AWS_REGION="${AWS_REGION:-us-east-1}"
read -rp "Max agent turns [10]: " AGENT_MAX_TURNS
AGENT_MAX_TURNS="${AGENT_MAX_TURNS:-10}"
read -rp "Git repo URL [https://github.com/autonomous-intelligence/autonomous-intelligence.git]: " REPO_URL
REPO_URL="${REPO_URL:-https://github.com/autonomous-intelligence/autonomous-intelligence.git}"
read -rp "Git branch [main]: " REPO_BRANCH
REPO_BRANCH="${REPO_BRANCH:-main}"

echo ""
echo "Installing system packages..."
dnf update -y
dnf install -y python3.12 python3.12-pip git

echo "Installing Node.js 20..."
curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
dnf install -y nodejs

echo "Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

echo "Installing Claude Code CLI..."
npm install -g @anthropic-ai/claude-code

# Swap
if [ ! -f /swapfile ]; then
    echo "Creating 1 GB swap file..."
    dd if=/dev/zero of=/swapfile bs=1M count=1024
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

echo "Creating application user..."
useradd -r -m -d /opt/discord-bot -s /bin/bash discord-bot || true

echo "Cloning repository..."
git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" /opt/discord-bot/repo
ln -sf /opt/discord-bot/repo/discord-bot /opt/discord-bot/discord-bot

echo "Writing .env file..."
cat > /opt/discord-bot/discord-bot/.env <<EOF
DISCORD_TOKEN=${DISCORD_TOKEN}
DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}
BEDROCK_MODEL=${BEDROCK_MODEL}
AWS_REGION=${AWS_REGION}
AGENT_MAX_TURNS=${AGENT_MAX_TURNS}
CLAUDE_CODE_USE_BEDROCK=1
EOF
chmod 600 /opt/discord-bot/discord-bot/.env

echo "Setting up Python environment..."
cd /opt/discord-bot/discord-bot
/usr/local/bin/uv venv --python python3.12
/usr/local/bin/uv pip install -e ".[bedrock]"

chown -R discord-bot:discord-bot /opt/discord-bot

echo "Installing systemd service..."
cp /opt/discord-bot/repo/claude-code-projects/claude-agent-ec2/config/discord-bot.service \
   /etc/systemd/system/discord-bot.service
systemctl daemon-reload
systemctl enable discord-bot
systemctl start discord-bot

echo ""
echo "=== Setup complete ==="
echo "Check status: sudo systemctl status discord-bot"
echo "View logs:    sudo journalctl -u discord-bot -f"

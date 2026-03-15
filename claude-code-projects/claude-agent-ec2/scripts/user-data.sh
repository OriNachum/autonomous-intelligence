#!/bin/bash
# Bootstrap script for EC2 instance (standalone version of CloudFormation UserData).
# This is the reference script — CloudFormation inlines a copy with Fn::Sub for parameters.
#
# Usage: Run as root on a fresh Amazon Linux 2023 instance.
# Required env vars: DISCORD_TOKEN, DISCORD_CHANNEL_ID, BEDROCK_MODEL, AWS_REGION, AGENT_MAX_TURNS, REPO_URL, REPO_BRANCH

set -euo pipefail
exec > /var/log/user-data.log 2>&1

echo "=== Starting bootstrap ==="

# Defaults
REPO_URL="${REPO_URL:-https://github.com/autonomous-intelligence/autonomous-intelligence.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
BEDROCK_MODEL="${BEDROCK_MODEL:-us.anthropic.claude-sonnet-4-20250514}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AGENT_MAX_TURNS="${AGENT_MAX_TURNS:-10}"

# --- System packages ---
dnf update -y
dnf install -y python3.12 python3.12-pip git

# Node.js 20 (required for claude CLI)
curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
dnf install -y nodejs

# --- uv (Python package manager) ---
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# --- Claude Code CLI ---
npm install -g @anthropic-ai/claude-code

# --- Swap (1 GB safety net for t2.micro) ---
if [ ! -f /swapfile ]; then
    dd if=/dev/zero of=/swapfile bs=1M count=1024
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

# --- Application user ---
useradd -r -m -d /opt/discord-bot -s /bin/bash discord-bot || true

# --- Clone repo ---
git clone --depth 1 -b "$REPO_BRANCH" "$REPO_URL" /opt/discord-bot/repo
ln -sf /opt/discord-bot/repo/discord-bot /opt/discord-bot/discord-bot

# --- Environment file ---
cat > /opt/discord-bot/discord-bot/.env <<EOF
DISCORD_TOKEN=${DISCORD_TOKEN}
DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}
BEDROCK_MODEL=${BEDROCK_MODEL}
AWS_REGION=${AWS_REGION}
AGENT_MAX_TURNS=${AGENT_MAX_TURNS}
CLAUDE_CODE_USE_BEDROCK=1
EOF
chmod 600 /opt/discord-bot/discord-bot/.env

# --- Python environment ---
cd /opt/discord-bot/discord-bot
/usr/local/bin/uv venv --python python3.12
/usr/local/bin/uv pip install -e ".[bedrock]"

# --- Fix ownership ---
chown -R discord-bot:discord-bot /opt/discord-bot

# --- Systemd service ---
cp /opt/discord-bot/repo/claude-code-projects/claude-agent-ec2/config/discord-bot.service \
   /etc/systemd/system/discord-bot.service

systemctl daemon-reload
systemctl enable discord-bot
systemctl start discord-bot

echo "=== Bootstrap complete ==="

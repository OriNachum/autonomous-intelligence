# Claude Agent EC2 — Discord Bot on Bedrock

Deploy the `discord-bot/` to an EC2 free-tier instance with the full Claude Code Agent SDK backed by AWS Bedrock.

## Architecture

- **EC2 t2.micro** (free tier) running Amazon Linux 2023
- **No SSH** — access via SSM Session Manager only
- **No inbound ports** — security group allows egress only
- **Bedrock** for Claude model inference (IAM role, no API keys)
- **systemd** for persistence across reboots
- **uv** for Python package management

```
EC2 (t2.micro)
├── discord-bot (Python + discord.py)
├── claude CLI (Node.js, required by claude-code-sdk)
└── systemd service (auto-restart, boot persistence)
    ↓ outbound only
    ├── Discord Gateway (wss://gateway.discord.gg)
    └── Bedrock API (bedrock-runtime.us-east-1.amazonaws.com)
```

## Prerequisites

1. **AWS Account** with free tier eligibility
2. **Bedrock model access** enabled for Claude models in your region
   - Go to AWS Console → Bedrock → Model access → Request access for Anthropic Claude
3. **Discord bot token** from [Discord Developer Portal](https://discord.com/developers/applications)
4. **AWS CLI v2** configured locally with permissions to create CloudFormation stacks

## Deploy with CloudFormation

```bash
aws cloudformation create-stack \
  --stack-name discord-bot-bedrock \
  --template-body file://cloudformation/stack.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameters \
    ParameterKey=DiscordToken,ParameterValue=YOUR_TOKEN \
    ParameterKey=DiscordChannelId,ParameterValue=YOUR_CHANNEL_ID \
    ParameterKey=BedrockModel,ParameterValue=us.anthropic.claude-sonnet-4-20250514 \
    ParameterKey=BedrockRegion,ParameterValue=us-east-1
```

Wait for stack creation:

```bash
aws cloudformation wait stack-create-complete --stack-name discord-bot-bedrock
```

## Connect via SSM

```bash
# Get instance ID from stack outputs
INSTANCE_ID=$(aws cloudformation describe-stacks \
  --stack-name discord-bot-bedrock \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
  --output text)

# Connect
aws ssm start-session --target "$INSTANCE_ID"
```

## Monitor

```bash
# Service status
sudo systemctl status discord-bot

# Live logs
sudo journalctl -u discord-bot -f

# Bootstrap log (first launch)
sudo cat /var/log/user-data.log

# Memory usage
free -m
```

## Update / Redeploy

From your local machine:

```bash
./scripts/deploy.sh discord-bot-bedrock
```

This pulls the latest code, reinstalls dependencies, and restarts the service via SSM.

## Manual Setup (without CloudFormation)

If you prefer to set up an existing EC2 instance manually:

```bash
# Connect via SSM, then:
sudo bash /path/to/scripts/setup-instance.sh
```

## Costs

| Resource | Free Tier | Notes |
|----------|-----------|-------|
| EC2 t2.micro | 750 hrs/mo (12 months) | ~$0 for first year |
| EBS 30 GB gp3 | 30 GB free (12 months) | ~$0 for first year |
| Data transfer | 100 GB/mo outbound | Discord + Bedrock traffic |
| **Bedrock** | **Pay per use** | ~$3/M input tokens, ~$15/M output tokens (Sonnet) |

Bedrock is the main ongoing cost. With `AGENT_MAX_TURNS=10` and typical Discord usage, expect $1-10/month for a small server.

## Troubleshooting

**Bot not starting:**

```bash
sudo journalctl -u discord-bot --no-pager -n 50
sudo cat /var/log/user-data.log
```

**Bedrock 403 / AccessDenied:**

- Verify model access is enabled in Bedrock console
- Check IAM role has `bedrock:InvokeModel` permission
- Confirm the model ID matches an available model in your region

**Bedrock 429 / Throttling:**

- Request RPM quota increase via AWS Support
- Reduce `AGENT_MAX_TURNS` to limit API calls per interaction

**Out of memory (t2.micro):**

- Check `free -m` — swap should be active (1 GB)
- Service has `MemoryMax=768M` limit in systemd
- Consider upgrading to t3.micro if consistently OOM

**SSM can't connect:**

- Instance needs outbound internet access (public subnet + IGW)
- IAM role must include `AmazonSSMManagedInstanceCore`
- SSM agent is pre-installed on Amazon Linux 2023

## File Structure

```
claude-agent-ec2/
├── README.md                              # This file
├── claude-code-bedrock-agent-sdk-concerns.md  # Design decisions & concerns
├── cloudformation/
│   └── stack.yaml                         # Full infrastructure stack
├── scripts/
│   ├── user-data.sh                       # EC2 bootstrap (reference)
│   ├── deploy.sh                          # Remote update via SSM
│   └── setup-instance.sh                  # Interactive manual setup
├── config/
│   ├── discord-bot.service                # systemd unit file
│   └── .env.example                       # Environment variables template
└── iam/
    └── bedrock-policy.json                # Scoped IAM policy
```

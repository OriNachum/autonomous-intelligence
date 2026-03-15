#!/bin/bash
# Deploy updates to the running EC2 instance via SSM.
#
# Usage: ./deploy.sh [stack-name]
#   stack-name: CloudFormation stack name (default: discord-bot-bedrock)

set -euo pipefail

STACK_NAME="${1:-discord-bot-bedrock}"

echo "Looking up instance ID from stack: $STACK_NAME"
INSTANCE_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" \
    --output text)

if [ -z "$INSTANCE_ID" ] || [ "$INSTANCE_ID" = "None" ]; then
    echo "Error: Could not find instance ID from stack $STACK_NAME"
    exit 1
fi

echo "Instance: $INSTANCE_ID"
echo "Sending update command via SSM..."

COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters 'commands=["cd /opt/discord-bot/repo && git pull && cd discord-bot && /usr/local/bin/uv pip install -e \".[bedrock]\" && sudo systemctl restart discord-bot && echo Update complete"]' \
    --query "Command.CommandId" \
    --output text)

echo "Command ID: $COMMAND_ID"
echo "Waiting for command to complete..."

aws ssm wait command-executed \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" 2>/dev/null || true

echo "Fetching output..."
aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --query "{Status: Status, Output: StandardOutputContent, Error: StandardErrorContent}" \
    --output table

echo "Done."

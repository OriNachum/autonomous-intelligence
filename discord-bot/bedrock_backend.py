"""Bedrock backend using Claude Code Agent SDK.

Uses the claude-code-sdk Python package which wraps the Claude Code CLI
with Bedrock as the model provider. Requires:
  - claude CLI installed (npm install -g @anthropic-ai/claude-code)
  - CLAUDE_CODE_USE_BEDROCK=1 environment variable
  - AWS credentials (IAM role or env vars)
"""

import os

from claude_code_sdk import ClaudeCodeOptions, query

BEDROCK_MODEL = os.getenv("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-20250514")
MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "10"))

SYSTEM_PROMPT = """You are a helpful assistant in a Discord server.
Keep responses concise and formatted for Discord markdown.
You do NOT have access to file system tools or bash."""


async def run_bedrock(message: str) -> str:
    """Run a query through the Claude Agent SDK backed by Bedrock."""
    result = []
    async for msg in query(
        prompt=message,
        options=ClaudeCodeOptions(
            model=BEDROCK_MODEL,
            permission_mode="plan",
            max_turns=MAX_TURNS,
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=[],
        ),
    ):
        if hasattr(msg, "content") and isinstance(msg.content, str):
            result.append(msg.content)
    return "\n".join(result)

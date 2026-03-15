# Claude Agent SDK on Bedrock (EC2) — Setup Notes & Concerns

> Use case: Non-code agent engine (Discord bot, task automation, structured workflows).
> Deployment: EC2 inside VPC. Internal use or open-source.
> NOT for coding tasks — leveraging the agent loop and tool orchestration for general-purpose automation.

---

## Overview

The Claude Agent SDK (formerly Claude Code SDK) provides the same agent loop, tool orchestration, and context management that power Claude Code — programmable in Python and TypeScript. It supports Amazon Bedrock natively via `CLAUDE_CODE_USE_BEDROCK=1` + AWS credentials.

For a non-code agent engine, the SDK gives you the agentic loop (multi-turn reasoning, tool calls, autonomous task completion) without you having to build that orchestration yourself. That's the real value here — not the file-system tools, but the loop.

---

## Concerns

### 1. Throttling — The #1 Issue

Bedrock enforces quotas on requests per minute (RPM) and tokens per minute (TPM). Each agent interaction can involve multiple API calls under the hood (the agent loop makes several round-trips per user request). Defaults: ~25 RPM for Opus 4.6 (upgradable to 500 RPM). A busy Discord server or multiple concurrent users will hit 429s fast. **Request quota increases from AWS proactively — before launch, not after.**

### 2. Latency Overhead

Slightly higher latency vs. direct Anthropic API due to AWS network hops. Expect 2-5s for simple queries (Sonnet), 5-15s for multi-step operations. For a Discord bot, this is manageable — but plan for it in UX (typing indicators, deferred responses).

### 3. Pin Your Model Versions

If you use model aliases without pinning, the SDK may attempt to use a newer model version not yet available in your Bedrock account, breaking things silently. **Non-negotiable for production.** Always pin to specific model version strings.

### 4. Licensing / Branding

Anthropic does not allow third-party products to appear as Claude Code or any Anthropic product. For internal Tipalti use: no issue. For open-source: fine — users bring their own AWS credentials, you're distributing code not the model. Just don't call it "Claude Code Bot" or imply it's an official Anthropic product. Maintain your own branding.

### 5. Security on EC2

By default, the Agent SDK exposes the full toolset (Read, Write, Edit, Bash, etc.). For a non-code agent engine, you don't need most of these. **Lock it down aggressively:**

- Use `allowed_tools` to whitelist only the tools your agent actually needs
- Use `disallowed_tools` to explicitly block Bash, Write, Edit if not needed
- Consider sandbox mode
- Define custom MCP tools for your specific workflows instead of relying on generic file-system access

Since you're inside a VPC, the network attack surface is already minimized. But tool access is the remaining risk vector.

### 6. Cost Unpredictability

Without limits, the agent loop runs until Claude decides it's done — which can be expensive on open-ended prompts. **Hard guardrails:**

- `max_budget_usd` — per-interaction cost cap
- `max_turns` — limit how many tool-call rounds the agent can make
- Discord-side: rate limit per user, queue requests, cap concurrency

### 7. Data Telemetry

The Agent SDK sends telemetry to Anthropic (usage data, conversation data, user feedback). This is opt-outable but on by default. If Tipalti has strict data governance, verify this is acceptable. **For open-source: document this in your README** so contributors and deployers know.

---

## VPC Deployment — What Changes

Running entirely inside a VPC eliminates most security concerns around public exposure:

- Bedrock endpoint stays within AWS's network (no public internet hops)
- IAM role on the EC2 instance handles auth to Bedrock — no API keys to manage
- No inbound internet access needed (Discord bot connects outbound via webhook/gateway)
- You control network boundaries completely

**This is a clean, intended deployment pattern.**

---

## Discord Bot — Specific Considerations

### Response Timing

Discord has interaction timeouts: 3 seconds for slash commands (extendable to 15 min with deferred responses). You'll need to:

1. Immediately defer the response
2. Let the agent loop run
3. Edit the message with results when done

Standard pattern, but plan for it in your bot framework.

### Natural Rate Limiting

Discord itself gives you built-in rate limiting (message cooldowns, per-user throttling). Layer this on top of your Bedrock RPM management: queue requests and process with a concurrency cap so you never exceed your quota.

### Open-Source Distribution

No licensing issues. You're distributing code, not the model. Users bring their own AWS credentials and Bedrock access. Just document: the telemetry behavior, required AWS permissions, and recommended budget caps.

---

## Non-Code Agent Engine — Architecture Notes

Since you're NOT using this for coding but as a general-purpose agent engine:

### What You're Actually Using

- **The agent loop** — multi-turn reasoning with tool calls, autonomous task completion
- **Tool orchestration** — define custom tools/MCP servers for your workflows
- **Context management** — the SDK handles conversation state and tool results

### What You Should Strip Out

- File-system tools (Read, Write, Edit) — unless your agent needs to work with files
- Bash tool — almost certainly not needed for non-code tasks
- Code-related defaults

### What You Should Add

- **Custom MCP tools** for your specific domain (Discord actions, database queries, API calls, etc.)
- **Structured output schemas** so agent responses are predictable and parseable
- **System prompts** tailored to your non-code use cases (not the default coding-focused ones)

### Honest Assessment

The Agent SDK is a solid choice here IF you need the agentic loop (multi-step reasoning, tool use, autonomous task completion). If your use cases are mostly single-turn Q&A, the raw Bedrock Messages API with tool_use is simpler and cheaper. But for multi-step workflows where the agent needs to reason, call tools, and iterate — the SDK saves you from building that orchestration yourself, which is non-trivial to get right.

---

## Quick Setup Checklist

- [ ] IAM role on EC2 with Bedrock invoke permissions
- [ ] `CLAUDE_CODE_USE_BEDROCK=1` env var
- [ ] Pin model version (don't use aliases)
- [ ] Set `max_budget_usd` and `max_turns` per interaction
- [ ] Whitelist only needed tools via `allowed_tools`
- [ ] Request Bedrock RPM quota increase from AWS
- [ ] Implement request queuing with concurrency cap
- [ ] Discord: deferred response pattern for slash commands
- [ ] Document telemetry behavior (especially if open-sourcing)
- [ ] Test under load before launch

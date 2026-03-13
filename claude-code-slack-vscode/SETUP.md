# Claude Code + Slack — VS Code Extension Setup

## Prerequisites

- **VS Code** 1.94+
- **Docker** (Docker Desktop or Colima) — the daemon runs in a container
- **Claude Code CLI** — `npm install -g @anthropic-ai/claude-code`

## Slack App Setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app (from manifest or scratch).

2. **Socket Mode** — Enable under *Settings > Socket Mode*. Generate an **app-level token** with `connections:write` scope (starts with `xapp-`).

3. **Event Subscriptions** — Enable and subscribe to bot events:
   - `message.im`
   - `message.groups`
   - `message.channels`

4. **OAuth & Permissions** — Add these bot token scopes:
   - `chat:write`
   - `reactions:read`
   - `reactions:write`
   - `im:history`
   - `im:write`
   - `users:read`

5. **Interactivity** — Enable (no URL needed for Socket Mode).

6. Install the app to your workspace. Copy the **Bot User OAuth Token** (`xoxb-...`).

7. Find your **Slack User ID**: click your profile in Slack → *More* → *Copy member ID*.

8. Note your **Signing Secret** from *Settings > Basic Information*.

## Install the Extension

```bash
cd claude-code-slack-vscode
npm install
npm run compile    # copies daemon files + builds
npm run package    # creates .vsix file
```

Install the `.vsix`:
- VS Code → Extensions → `...` → *Install from VSIX...*
- Or: `code --install-extension claude-code-slack-0.1.0.vsix`

## Configure Tokens

Open the command palette (`Cmd+Shift+P`) and run:

> **Claude+Slack: Set Slack Tokens**

Enter all four values when prompted:
1. Bot token (`xoxb-...`)
2. App-level token (`xapp-...`)
3. Signing secret
4. Slack user ID (`U...`)

Tokens are stored securely in VS Code's SecretStorage (keychain-backed). The user ID is stored in VS Code settings.

## How It Works

On activation, the extension:
1. Loads tokens from SecretStorage into the environment
2. Starts a Docker container (`claude-slack-daemon`) that holds the Socket Mode connection
3. The container mounts `~/.claude/ipc/slack/` for file-based IPC with the extension
4. Messages flow bidirectionally between VS Code and Slack

## Manual Docker Commands

```bash
# Check if daemon is running
docker ps --filter name=claude-slack-daemon

# View daemon logs
docker logs -f claude-slack-daemon

# Restart daemon
docker compose -f ~/.vscode/extensions/custom.claude-code-slack-*/daemon/docker-compose.yml restart

# Stop daemon
docker stop claude-slack-daemon
```

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `claudeSlack.slackUserId` | `""` | Target Slack user ID |
| `claudeSlack.slackEnabled` | `true` | Enable/disable Slack integration |
| `claudeSlack.selectedModel` | `claude-sonnet-4-6` | Claude model to use |
| `claudeSlack.permissionMode` | `default` | Tool permission mode |
| `claudeSlack.slackBufferIntervalMs` | `1500` | Message buffer flush interval |

## Troubleshooting

**Extension activates but no Slack connection:**
- Check the output panel: *View > Output* → select "Claude + Slack"
- Verify tokens are set: re-run "Set Slack Tokens" command
- Ensure Docker is running: `docker info`

**Docker daemon won't start:**
- Check Docker is installed and running
- Try manually: `cd <extension-path>/daemon && docker compose up --build`
- Check logs: `docker logs claude-slack-daemon`

**Messages not appearing in Slack:**
- Verify the bot token has the required scopes
- Check that your Slack user ID matches the configured value
- Look at `~/.claude/ipc/slack/daemon.log` for routing errors

**Dev mode (no Docker):**
- If Docker is unavailable, the extension falls back to spawning `daemon.py` directly with Python
- Requires Python 3.11+ and dependencies: `pip install -r requirements.txt`

import "dotenv/config";

export interface Config {
  discordToken: string;
  channelId: string;
  model: string;
  permissionMode: string;
  bufferIntervalMs: number;
  maxConcurrentSessions: number;
  sessionTimeoutMs: number;
  systemPrompt: string | undefined;
}

export function loadConfig(): Config {
  const discordToken = process.env.DISCORD_TOKEN;
  const channelId = process.env.DISCORD_CHANNEL_ID;

  if (!discordToken) {
    throw new Error("DISCORD_TOKEN is required in environment");
  }
  if (!channelId) {
    throw new Error("DISCORD_CHANNEL_ID is required in environment");
  }

  return {
    discordToken,
    channelId,
    model: process.env.MODEL ?? "claude-sonnet-4-6",
    permissionMode: process.env.PERMISSION_MODE ?? "acceptEdits",
    bufferIntervalMs: parseInt(process.env.BUFFER_INTERVAL_MS ?? "1500", 10),
    maxConcurrentSessions: parseInt(process.env.MAX_CONCURRENT_SESSIONS ?? "5", 10),
    sessionTimeoutMs: parseInt(process.env.SESSION_TIMEOUT_MS ?? "3600000", 10),
    systemPrompt: process.env.SYSTEM_PROMPT || undefined,
  };
}

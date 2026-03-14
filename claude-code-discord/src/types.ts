import type { SDKMessage } from "@anthropic-ai/claude-agent-sdk";

export type { SDKMessage };

export interface PermissionRequest {
  id: string;
  toolName: string;
  toolInput: unknown;
  resolve: (approved: boolean, updatedInput?: Record<string, unknown>) => void;
}

export interface SessionInfo {
  sessionId: string;
  model: string;
  cwd: string;
  threadId?: string;
  startedAt: number;
}

export interface PendingQuestion {
  permissionId: string;
  question: string;
  toolInput: unknown;
  threadId: string;
}

export interface DiscordAttachment {
  name: string;
  url: string;
  contentType: string | null;
  size: number;
}

export interface Session {
  threadId: string;
  cwd: string;
  sdkClient: import("./sdk-client.js").SDKClient;
  discordThread: import("./discord-thread.js").DiscordThread;
  router: import("./message-router.js").MessageRouter;
  info: SessionInfo | null;
  lastActivity: number;
  timeoutTimer: ReturnType<typeof setTimeout> | null;
}

import type { SDKMessage } from "@anthropic-ai/claude-agent-sdk";

// Re-export SDK types we use throughout
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
  slackThreadTs?: string;
  slackChannel?: string;
  startedAt: number;
}

export type MessageSource = "webview" | "slack";

export interface UserMessage {
  text: string;
  source: MessageSource;
  timestamp: number;
}

// Messages sent from extension → webview
export type ExtensionToWebviewMessage =
  | { type: "assistant"; content: AssistantContent[] }
  | { type: "user"; text: string; source: MessageSource }
  | { type: "system"; text: string }
  | { type: "toolUse"; toolName: string; toolInput: unknown; id: string }
  | { type: "toolResult"; id: string; output: string; isError: boolean }
  | { type: "thinking"; text: string }
  | { type: "permissionRequest"; id: string; toolName: string; toolInput: unknown }
  | { type: "permissionResolved"; id: string; approved: boolean }
  | { type: "sessionInfo"; info: SessionInfo }
  | { type: "streamText"; text: string; messageId: string }
  | { type: "streamEnd"; messageId: string }
  | { type: "slackStatus"; connected: boolean }
  | { type: "result"; subtype: string; cost: number; duration: number }
  | { type: "clear" };

// Messages sent from webview → extension
export type WebviewToExtensionMessage =
  | { type: "sendMessage"; text: string }
  | { type: "approvePermission"; id: string }
  | { type: "denyPermission"; id: string; message?: string }
  | { type: "stopSession" }
  | { type: "newSession" }
  | { type: "setModel"; model: string }
  | { type: "ready" };

export interface AssistantContent {
  type: "text" | "tool_use" | "thinking";
  text?: string;
  id?: string;
  name?: string;
  input?: unknown;
}

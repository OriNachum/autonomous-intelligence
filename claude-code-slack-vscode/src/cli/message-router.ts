import type { SDKMessage } from "@anthropic-ai/claude-agent-sdk";
import type {
  ExtensionToWebviewMessage,
  AssistantContent,
  PermissionRequest,
  SessionInfo,
} from "../types";

export interface MessageSink {
  postToWebview(message: ExtensionToWebviewMessage): void;
  postToSlack(text: string, options?: { emoji?: string; isCode?: boolean }): void;
  postPermissionToSlack?(requestId: string, toolName: string, inputStr: string, toolInput?: unknown): void;
  postQuestionToSlack?(questionId: string, question: string, options: { label: string; description?: string }[]): void;
}

/**
 * Routes SDK messages to both the webview and Slack.
 * Slack failures never block the webview — fire-and-forget.
 */
export class MessageRouter {
  private sink: MessageSink;
  private currentStreamId: string | null = null;
  private streamCounter = 0;
  private isStreaming = false;
  private hadThinkingStream = false;

  constructor(sink: MessageSink) {
    this.sink = sink;
  }

  /**
   * Process an SDKMessage and fan it out to webview + Slack.
   */
  routeMessage(message: SDKMessage): void {
    switch (message.type) {
      case "system":
        this.handleSystem(message);
        break;
      case "assistant":
        this.handleAssistant(message);
        break;
      case "user":
        // User messages are already displayed by the sender
        break;
      case "result":
        this.handleResult(message);
        break;
      case "stream_event":
        this.handleStreamEvent(message);
        break;
    }
  }

  /**
   * Route a permission request to both webview and Slack.
   */
  routePermissionRequest(request: PermissionRequest): void {
    this.sink.postToWebview({
      type: "permissionRequest",
      id: request.id,
      toolName: request.toolName,
      toolInput: request.toolInput,
    });

    // Post to Slack with Block Kit buttons if available, otherwise plain text
    const inputStr = formatToolInput(request.toolName, request.toolInput);
    if (this.sink.postPermissionToSlack) {
      this.sink.postPermissionToSlack(request.id, request.toolName, inputStr, request.toolInput);
    } else {
      this.sink.postToSlack(
        `*Claude wants to use \`${request.toolName}\`:*\n${inputStr}\n\nApprove? (yes/no)`,
        { emoji: "hammer_and_wrench" }
      );
    }
  }

  /**
   * Route an AskUserQuestion to both webview and Slack.
   */
  routeQuestion(
    questionId: string,
    question: string,
    options: { label: string; description?: string }[]
  ): void {
    // Post to Slack with Block Kit buttons if available
    if (this.sink.postQuestionToSlack) {
      this.sink.postQuestionToSlack(questionId, question, options);
    } else {
      const optionStr = options.map((o) => `• ${o.label}`).join("\n");
      this.sink.postToSlack(`*${question}*\n${optionStr}`);
    }
  }

  /**
   * Route a permission resolution.
   */
  routePermissionResolved(id: string, approved: boolean): void {
    this.sink.postToWebview({
      type: "permissionResolved",
      id,
      approved,
    });
  }

  /**
   * Route session info.
   */
  routeSessionInfo(info: SessionInfo): void {
    this.sink.postToWebview({ type: "sessionInfo", info });
  }

  /**
   * Route a notification from the SDK.
   */
  routeNotification(title: string, message: string): void {
    this.sink.postToWebview({ type: "system", text: `${title}: ${message}` });
    this.sink.postToSlack(`*${title}*\n${message}`, { emoji: "bell" });
  }

  private handleSystem(message: SDKMessage): void {
    if ((message as any).subtype === "init") {
      this.sink.postToWebview({
        type: "system",
        text: `Session started (${(message as any).model ?? "unknown model"})`,
      });
    }
  }

  private handleAssistant(message: SDKMessage): void {
    const msg = message as any;
    const apiMessage = msg.message;
    if (!apiMessage?.content) return;

    const textParts: string[] = [];

    for (const block of apiMessage.content) {
      if (block.type === "text") {
        textParts.push(block.text);
        // If we were streaming this text, finalize the stream bubble
        // instead of creating a duplicate
        if (this.isStreaming && this.currentStreamId) {
          this.sink.postToWebview({
            type: "streamEnd",
            messageId: this.currentStreamId,
          });
          this.isStreaming = false;
          this.currentStreamId = null;
        } else {
          // No streaming happened (e.g. tool results) — show as regular message
          this.sink.postToWebview({
            type: "assistant",
            content: [{ type: "text", text: block.text }],
          });
        }
      } else if (block.type === "tool_use") {
        // Send tool use to webview
        this.sink.postToWebview({
          type: "toolUse",
          toolName: block.name,
          toolInput: block.input,
          id: block.id,
        });

        // Send tool use to Slack
        const inputStr = formatToolInput(block.name, block.input);
        this.sink.postToSlack(`\`${block.name}\`: ${inputStr}`, {
          emoji: "gear",
        });
      } else if (block.type === "thinking") {
        // Skip if thinking was already streamed via deltas
        if (!this.hadThinkingStream) {
          this.sink.postToWebview({ type: "thinking", text: block.thinking });
        }
        this.hadThinkingStream = false;
      }
    }

    // Send text parts to Slack (always — Slack doesn't get streaming)
    const fullText = textParts.join("\n");
    if (fullText.trim()) {
      this.sink.postToSlack(fullText);
    }
  }

  private handleResult(message: SDKMessage): void {
    const msg = message as any;
    this.sink.postToWebview({
      type: "result",
      subtype: msg.subtype,
      cost: msg.total_cost_usd ?? 0,
      duration: msg.duration_ms ?? 0,
    });

    const costStr = msg.total_cost_usd
      ? ` ($${msg.total_cost_usd.toFixed(4)})`
      : "";
    const durationStr = msg.duration_ms
      ? ` in ${(msg.duration_ms / 1000).toFixed(1)}s`
      : "";
    this.sink.postToSlack(`_Session complete${durationStr}${costStr}_`);
  }

  private handleStreamEvent(message: SDKMessage): void {
    const msg = message as any;
    const event = msg.event;
    if (!event) return;

    // Handle streaming text deltas
    if (event.type === "content_block_delta") {
      if (event.delta?.type === "text_delta" && event.delta.text) {
        // Use a stable ID for the entire streaming turn
        if (!this.currentStreamId) {
          this.currentStreamId = `stream_${++this.streamCounter}`;
        }
        this.isStreaming = true;

        this.sink.postToWebview({
          type: "streamText",
          text: event.delta.text,
          messageId: this.currentStreamId,
        });
      } else if (
        event.delta?.type === "thinking_delta" &&
        event.delta.thinking
      ) {
        this.hadThinkingStream = true;
        this.sink.postToWebview({
          type: "thinking",
          text: event.delta.thinking,
        });
      }
    } else if (event.type === "message_stop") {
      // Don't send streamEnd here — let handleAssistant finalize it
      // so we avoid the duplicate message issue
    } else if (event.type === "message_start") {
      // New assistant message starting — reset stream state
      this.currentStreamId = null;
      this.isStreaming = false;
      this.hadThinkingStream = false;
    }
  }
}

function formatToolInput(toolName: string, input: unknown): string {
  if (!input || typeof input !== "object") return String(input);

  const inp = input as Record<string, unknown>;

  switch (toolName) {
    case "Bash":
      return `\`\`\`\n${truncate(String(inp.command ?? ""), 2000)}\n\`\`\``;
    case "Read":
      return `\`${inp.file_path}\``;
    case "Write":
      return `\`${inp.file_path}\` (${String(inp.content ?? "").length} chars)`;
    case "Edit":
      return `\`${inp.file_path}\``;
    case "Glob":
      return `\`${inp.pattern}\`${inp.path ? ` in \`${inp.path}\`` : ""}`;
    case "Grep":
      return `\`${inp.pattern}\`${inp.path ? ` in \`${inp.path}\`` : ""}`;
    case "WebSearch":
      return `"${inp.query}"`;
    case "WebFetch":
      return `\`${inp.url}\``;
    case "Task":
      return `${inp.description}: ${truncate(String(inp.prompt ?? ""), 200)}`;
    case "EnterPlanMode":
      return "";
    case "ExitPlanMode":
      return "";
    case "Skill":
      return `\`${inp.skill}\`${inp.args ? ` ${inp.args}` : ""}`;
    case "TaskCreate":
    case "TodoWrite":
      return truncate(String(inp.subject ?? inp.content ?? JSON.stringify(input)), 200);
    case "TaskUpdate":
      return `${inp.status ?? ""}${inp.subject ? ` — ${inp.subject}` : ""}`;
    case "TaskList":
    case "TaskGet":
      return "";
    case "NotebookEdit":
      return `\`${inp.notebook_path}\``;
    default:
      return formatDefaultInput(inp);
  }
}

/** Compact summary for unknown tools — shows key fields without raw JSON dumps. */
function formatDefaultInput(inp: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, val] of Object.entries(inp)) {
    if (val === undefined || val === null) continue;
    if (typeof val === "string") {
      parts.push(`${key}: ${truncate(val, 120)}`);
    } else if (typeof val === "boolean" || typeof val === "number") {
      parts.push(`${key}: ${val}`);
    } else {
      parts.push(`${key}: ${truncate(JSON.stringify(val), 120)}`);
    }
    if (parts.length >= 4) break; // limit to 4 fields
  }
  return parts.length ? parts.join("\n") : "{}";
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\n... (truncated)";
}

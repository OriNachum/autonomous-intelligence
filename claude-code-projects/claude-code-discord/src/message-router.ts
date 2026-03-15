import type { SDKMessage, SessionInfo } from "./types.js";
import { formatToolInput, formatResult } from "./message-formatter.js";

/**
 * Sink interface — Discord thread posting methods.
 */
export interface MessageSink {
  postText(text: string): void;
  postToolUse(toolName: string, inputStr: string): void;
  postPermissionRequest(
    requestId: string,
    toolName: string,
    inputStr: string,
    toolInput?: unknown
  ): void;
  postQuestion(
    questionId: string,
    question: string,
    options: { label: string; description?: string }[]
  ): void;
  postResult(text: string): void;
  postSessionInfo(info: SessionInfo): void;
}

/**
 * Routes SDK messages to the Discord thread sink.
 */
export class MessageRouter {
  private sink: MessageSink;

  constructor(sink: MessageSink) {
    this.sink = sink;
  }

  /**
   * Process an SDKMessage and route it to the Discord thread.
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
        // We don't do real-time streaming in Discord — handleAssistant handles finalized text
        break;
    }
  }

  /**
   * Route a permission request.
   */
  routePermissionRequest(
    requestId: string,
    toolName: string,
    toolInput: unknown
  ): void {
    const inputStr = formatToolInput(toolName, toolInput);
    this.sink.postPermissionRequest(requestId, toolName, inputStr, toolInput);
  }

  /**
   * Route a question (AskUserQuestion).
   */
  routeQuestion(
    questionId: string,
    question: string,
    options: { label: string; description?: string }[]
  ): void {
    this.sink.postQuestion(questionId, question, options);
  }

  /**
   * Route session info.
   */
  routeSessionInfo(info: SessionInfo): void {
    this.sink.postSessionInfo(info);
  }

  /**
   * Route a notification.
   */
  routeNotification(title: string, message: string): void {
    this.sink.postText(`**${title}**\n${message}`);
  }

  private handleSystem(message: SDKMessage): void {
    if ((message as any).subtype === "init") {
      // Session info is handled via sessionInit event
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
      } else if (block.type === "tool_use") {
        const inputStr = formatToolInput(block.name, block.input);
        this.sink.postToolUse(block.name, inputStr);
      } else if (block.type === "thinking") {
        // Post thinking as spoiler in Discord
        if (block.thinking) {
          const thinkText = block.thinking.length > 500
            ? block.thinking.slice(0, 500) + "..."
            : block.thinking;
          this.sink.postText(`||**Thinking:** ${thinkText}||`);
        }
      }
    }

    const fullText = textParts.join("\n");
    if (fullText.trim()) {
      this.sink.postText(fullText);
    }
  }

  private handleResult(message: SDKMessage): void {
    const msg = message as any;
    const text = formatResult(
      msg.subtype ?? "complete",
      msg.total_cost_usd ?? 0,
      msg.duration_ms ?? 0
    );
    this.sink.postResult(text);
  }
}

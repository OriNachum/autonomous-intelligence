import * as vscode from "vscode";
import { SDKClient, type SDKClientOptions } from "./sdk-client";
import { MessageRouter, type MessageSink } from "./message-router";
import type {
  SessionInfo,
  ExtensionToWebviewMessage,
  MessageSource,
} from "../types";
import type { SlackFileMetadata } from "../slack/slack-client";

/**
 * Orchestrates the lifecycle of a Claude session:
 * SDKClient ↔ MessageRouter ↔ (Webview + Slack)
 */
export class SessionManager {
  private sdkClient: SDKClient;
  private router: MessageRouter;
  private sessionInfo: SessionInfo | null = null;
  private _onWebviewMessage: ((msg: ExtensionToWebviewMessage) => void) | null =
    null;
  private _onSlackMessage:
    | ((text: string, options?: { emoji?: string; isCode?: boolean }) => void)
    | null = null;
  private _onSlackPermission:
    | ((requestId: string, toolName: string, inputStr: string, toolInput?: unknown) => void)
    | null = null;
  private _onSlackQuestion:
    | ((questionId: string, question: string, options: { label: string; description?: string }[]) => void)
    | null = null;
  /** Maps questionId → permissionId for AskUserQuestion flow */
  private pendingQuestions = new Map<string, { permissionId: string; question: string; toolInput: unknown }>();
  private fileDownloader: ((url: string) => Promise<Buffer>) | null = null;

  constructor() {
    this.sdkClient = new SDKClient();

    const sink: MessageSink = {
      postToWebview: (msg) => this._onWebviewMessage?.(msg),
      postToSlack: (text, options) => this._onSlackMessage?.(text, options),
      postPermissionToSlack: (requestId, toolName, inputStr, toolInput) =>
        this._onSlackPermission?.(requestId, toolName, inputStr, toolInput),
      postQuestionToSlack: (questionId, question, options) =>
        this._onSlackQuestion?.(questionId, question, options),
    };
    this.router = new MessageRouter(sink);

    this.setupListeners();
  }

  get isRunning(): boolean {
    return this.sdkClient.isRunning;
  }

  get currentSession(): SessionInfo | null {
    return this.sessionInfo;
  }

  /**
   * Register the webview message handler.
   */
  onWebviewMessage(handler: (msg: ExtensionToWebviewMessage) => void): void {
    this._onWebviewMessage = handler;
  }

  /**
   * Register the Slack message handler.
   */
  onSlackMessage(
    handler: (
      text: string,
      options?: { emoji?: string; isCode?: boolean }
    ) => void
  ): void {
    this._onSlackMessage = handler;
  }

  /**
   * Register the Slack permission request handler (Block Kit buttons).
   */
  onSlackPermission(
    handler: (requestId: string, toolName: string, inputStr: string, toolInput?: unknown) => void
  ): void {
    this._onSlackPermission = handler;
  }

  /**
   * Register the Slack question handler (Block Kit buttons).
   */
  onSlackQuestion(
    handler: (questionId: string, question: string, options: { label: string; description?: string }[]) => void
  ): void {
    this._onSlackQuestion = handler;
  }

  /**
   * Set a file downloader function (injected from SlackClient).
   */
  setFileDownloader(fn: (url: string) => Promise<Buffer>): void {
    this.fileDownloader = fn;
    this.sdkClient.setFileDownloader(fn);
  }

  /**
   * Send a user message to Claude (from webview or Slack).
   */
  async sendMessage(text: string, source: MessageSource, files?: SlackFileMetadata[]): Promise<void> {
    // Echo to webview
    const fileNames = files?.map((f) => f.name) ?? [];
    const echoText = fileNames.length
      ? `${text}\n_Attached: ${fileNames.join(", ")}_`
      : text;
    this._onWebviewMessage?.({
      type: "user",
      text: echoText,
      source,
    });

    const config = vscode.workspace.getConfiguration("claudeSlack");
    const model = config.get<string>("selectedModel") ?? "claude-sonnet-4-6";
    const permissionMode = config.get<string>("permissionMode") ?? "default";
    const cwd =
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();

    const options: SDKClientOptions = {
      model,
      cwd,
      permissionMode,
      resume: this.sdkClient.currentSessionId ?? undefined,
    };

    await this.sdkClient.sendMessage(text, options, files);
  }

  /**
   * Approve or deny a permission request.
   */
  resolvePermission(
    id: string,
    approved: boolean,
    _source: MessageSource
  ): void {
    this.sdkClient.resolvePermission(id, approved);
    this.router.routePermissionResolved(id, approved);
  }

  /**
   * Resolve an AskUserQuestion by approving the permission with the answer
   * injected into updatedInput.
   */
  resolveQuestion(questionId: string, answer: string): void {
    const pending = this.pendingQuestions.get(questionId);
    if (!pending) return;

    this.pendingQuestions.delete(questionId);

    // Build updatedInput with the answer
    const input = (pending.toolInput ?? {}) as Record<string, unknown>;
    const updatedInput = {
      ...input,
      answers: { [pending.question]: answer },
    };

    this.sdkClient.resolvePermissionWithInput(pending.permissionId, updatedInput);
    this.router.routePermissionResolved(pending.permissionId, true);
  }

  /**
   * Stop the current session.
   */
  async stopSession(): Promise<void> {
    await this.sdkClient.stop();
    this.sessionInfo = null;
    this._onWebviewMessage?.({ type: "system", text: "Session stopped" });
  }

  /**
   * Start a new session (clears previous).
   */
  async newSession(): Promise<void> {
    await this.sdkClient.stop();
    this.sessionInfo = null;
    this._onWebviewMessage?.({ type: "clear" });
    this._onWebviewMessage?.({
      type: "system",
      text: "New session — type a message to begin",
    });
  }

  /**
   * Change the model.
   */
  async setModel(model: string): Promise<void> {
    await this.sdkClient.setModel(model);
  }

  dispose(): void {
    this.sdkClient.stop().catch(() => {});
  }

  private setupListeners(): void {
    this.sdkClient.on("message", (message) => {
      this.router.routeMessage(message);
    });

    this.sdkClient.on("sessionInit", (info: SessionInfo) => {
      this.sessionInfo = info;
      this.router.routeSessionInfo(info);
    });

    this.sdkClient.on("permissionRequest", (request) => {
      // Intercept AskUserQuestion: show answer buttons instead of Approve/Deny
      if (request.toolName === "AskUserQuestion") {
        const input = request.toolInput as any;
        const questions = input?.questions ?? [];
        if (questions.length > 0) {
          const q = questions[0];
          const questionId = `q_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
          this.pendingQuestions.set(questionId, {
            permissionId: request.id,
            question: q.question,
            toolInput: request.toolInput,
          });
          // Route as question buttons to Slack (not Approve/Deny)
          this.router.routeQuestion(questionId, q.question, q.options ?? []);
          // Show question text in webview so user understands what's being asked
          const optionsList = (q.options ?? [])
            .map((o: any, i: number) => `${i + 1}. **${o.label}**${o.description ? ` — ${o.description}` : ""}`)
            .join("\n");
          this._onWebviewMessage?.({
            type: "assistant",
            content: [{ type: "text", text: `**${q.question}**\n${optionsList}\n\n_Reply with your choice, or use Slack buttons._` }],
          });
          return;
        }
      }
      this.router.routePermissionRequest(request);
    });

    this.sdkClient.on("notification", ({ title, message }) => {
      this.router.routeNotification(title, message);
    });

    this.sdkClient.on("error", (err) => {
      const errorMsg =
        err instanceof Error ? err.message : "Unknown error occurred";
      this._onWebviewMessage?.({
        type: "system",
        text: `Error: ${errorMsg}`,
      });
    });

    this.sdkClient.on("turnComplete", () => {
      // No-op for now; could track turn count
    });
  }
}

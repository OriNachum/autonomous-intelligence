import { EventEmitter } from "events";
import {
  query,
  type SDKMessage,
  type Query,
  type CanUseTool,
  type PermissionResult,
  type HookCallbackMatcher,
  type HookEvent,
} from "@anthropic-ai/claude-agent-sdk";
import type { PermissionRequest, SessionInfo } from "../types";
import type { SlackFileMetadata } from "../slack/slack-client";

export interface SDKClientOptions {
  model: string;
  cwd: string;
  permissionMode?: string;
  systemPrompt?: string;
  resume?: string;
}

/**
 * Wraps the @anthropic-ai/claude-agent-sdk, managing the CLI process lifecycle
 * and emitting typed messages for consumption by the MessageRouter.
 */
const IMAGE_MIMETYPES = new Set(["image/jpeg", "image/png", "image/gif", "image/webp"]);
const MAX_IMAGE_BYTES = 20 * 1024 * 1024; // 20MB
const MAX_TEXT_BYTES = 512 * 1024; // 512KB

export class SDKClient extends EventEmitter {
  private currentQuery: Query | null = null;
  private abortController: AbortController | null = null;
  private sessionId: string | null = null;
  private pendingPermissions = new Map<string, PermissionRequest>();
  private permissionCounter = 0;
  private _isRunning = false;
  private fileDownloader: ((url: string) => Promise<Buffer>) | null = null;

  get isRunning(): boolean {
    return this._isRunning;
  }

  get currentSessionId(): string | null {
    return this.sessionId;
  }

  /**
   * Set a file downloader function for fetching Slack files.
   */
  setFileDownloader(fn: (url: string) => Promise<Buffer>): void {
    this.fileDownloader = fn;
  }

  /**
   * Start a new query (conversation turn). Streams SDK messages via 'message' events.
   */
  async sendMessage(prompt: string, options: SDKClientOptions, files?: SlackFileMetadata[]): Promise<void> {
    if (this._isRunning) {
      // Queue as follow-up — interrupt the current query and restart
      await this.interrupt();
    }

    this.abortController = new AbortController();
    this._isRunning = true;

    const canUseTool: CanUseTool = async (
      toolName: string,
      toolInput: unknown,
      { signal }
    ): Promise<PermissionResult> => {
      const id = `perm_${++this.permissionCounter}`;

      return new Promise<PermissionResult>((resolve) => {
        const request: PermissionRequest = {
          id,
          toolName,
          toolInput,
          resolve: (approved: boolean, customInput?: Record<string, unknown>) => {
            this.pendingPermissions.delete(id);
            if (approved) {
              resolve({
                behavior: "allow",
                updatedInput: customInput ?? (toolInput as Record<string, unknown>),
              });
            } else {
              resolve({
                behavior: "deny",
                message: "User denied permission",
              });
            }
          },
        };

        this.pendingPermissions.set(id, request);
        this.emit("permissionRequest", request);

        // Auto-deny on abort
        signal.addEventListener("abort", () => {
          if (this.pendingPermissions.has(id)) {
            this.pendingPermissions.delete(id);
            resolve({ behavior: "deny", message: "Session aborted" });
          }
        });
      });
    };

    // Build hooks for notifications and session lifecycle
    const hooks: Partial<Record<HookEvent, HookCallbackMatcher[]>> = {
      Notification: [
        {
          hooks: [
            async (input) => {
              if (input.hook_event_name === "Notification") {
                this.emit("notification", {
                  title: (input as any).title,
                  message: (input as any).message,
                });
              }
              return { continue: true };
            },
          ],
        },
      ],
      Stop: [
        {
          hooks: [
            async () => {
              this.emit("agentStop");
              return { decision: "approve" as const };
            },
          ],
        },
      ],
    };

    // Build multimodal prompt if files are attached
    const resolvedPrompt = files?.length
      ? await this.buildMultiModalPrompt(prompt, files)
      : prompt;

    const queryOptions: Parameters<typeof query>[0] = {
      prompt: resolvedPrompt,
      options: {
        abortController: this.abortController,
        cwd: options.cwd,
        model: options.model,
        permissionMode: (options.permissionMode as any) ?? "default",
        canUseTool,
        hooks,
        resume: options.resume ?? this.sessionId ?? undefined,
        includePartialMessages: true,
        tools: { type: "preset", preset: "claude_code" },
        systemPrompt: options.systemPrompt
          ? { type: "preset", preset: "claude_code", append: options.systemPrompt }
          : { type: "preset", preset: "claude_code" },
        // Skip 'user' settings source to avoid loading ~/.claude/settings.json hooks
        // which conflict with our in-process SDK hooks
        settingSources: ["project", "local"],
      },
    };

    try {
      this.currentQuery = query(queryOptions);

      for await (const message of this.currentQuery) {
        // Capture session ID from init message
        if (
          message.type === "system" &&
          (message as any).subtype === "init" &&
          message.session_id
        ) {
          this.sessionId = message.session_id;
          const info: SessionInfo = {
            sessionId: message.session_id,
            model: (message as any).model ?? options.model,
            cwd: (message as any).cwd ?? options.cwd,
            startedAt: Date.now(),
          };
          this.emit("sessionInit", info);
        }

        this.emit("message", message);
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        this.emit("error", err);
      }
    } finally {
      this._isRunning = false;
      this.currentQuery = null;
      this.abortController = null;
      this.emit("turnComplete");
    }
  }

  /**
   * Resolve a pending permission request.
   */
  resolvePermission(id: string, approved: boolean): void {
    const request = this.pendingPermissions.get(id);
    if (request) {
      request.resolve(approved);
    }
  }

  /**
   * Resolve a pending permission with custom updatedInput (e.g. AskUserQuestion answers).
   */
  resolvePermissionWithInput(id: string, updatedInput: Record<string, unknown>): void {
    const request = this.pendingPermissions.get(id);
    if (request) {
      request.resolve(true, updatedInput);
    }
  }

  /**
   * Interrupt the current query.
   */
  async interrupt(): Promise<void> {
    if (this.currentQuery) {
      try {
        await this.currentQuery.interrupt();
      } catch {
        // Fallback to abort
        this.abortController?.abort();
      }
    }
  }

  /**
   * Fully stop and reset. Clears session.
   */
  async stop(): Promise<void> {
    await this.interrupt();
    // Deny all pending permissions
    for (const [, req] of this.pendingPermissions) {
      req.resolve(false);
    }
    this.pendingPermissions.clear();
    this.sessionId = null;
    this._isRunning = false;
  }

  /**
   * Change model for future queries.
   */
  async setModel(model: string): Promise<void> {
    if (this.currentQuery) {
      await this.currentQuery.setModel(model);
    }
  }

  /**
   * Get supported models.
   */
  async supportedModels(): Promise<any[]> {
    if (this.currentQuery) {
      return this.currentQuery.supportedModels();
    }
    return [];
  }

  /**
   * Build a multimodal prompt string with file content inlined.
   * Downloads each file and builds appropriate content for the prompt.
   */
  private async buildMultiModalPrompt(
    text: string,
    files: SlackFileMetadata[]
  ): Promise<string> {
    if (!this.fileDownloader) return text;

    const parts: string[] = [text];

    for (const file of files) {
      try {
        if (IMAGE_MIMETYPES.has(file.mimetype)) {
          if (file.size > MAX_IMAGE_BYTES) {
            parts.push(`[Skipped image "${file.name}": ${(file.size / 1024 / 1024).toFixed(1)}MB exceeds 20MB limit]`);
            continue;
          }
          const buf = await this.fileDownloader(file.url_private_download);
          const b64 = buf.toString("base64");
          parts.push(`[Image: ${file.name}]\ndata:${file.mimetype};base64,${b64}`);
        } else if (file.mimetype === "application/pdf") {
          if (file.size > MAX_IMAGE_BYTES) {
            parts.push(`[Skipped PDF "${file.name}": ${(file.size / 1024 / 1024).toFixed(1)}MB exceeds 20MB limit]`);
            continue;
          }
          const buf = await this.fileDownloader(file.url_private_download);
          const b64 = buf.toString("base64");
          parts.push(`[PDF: ${file.name}]\ndata:application/pdf;base64,${b64}`);
        } else if (isTextMimetype(file.mimetype) || isTextExtension(file.filetype)) {
          if (file.size > MAX_TEXT_BYTES) {
            parts.push(`[Skipped file "${file.name}": ${(file.size / 1024).toFixed(0)}KB exceeds 512KB limit]`);
            continue;
          }
          const buf = await this.fileDownloader(file.url_private_download);
          const content = buf.toString("utf-8");
          parts.push(`[File: ${file.name}]\n\`\`\`\n${content}\n\`\`\``);
        } else {
          parts.push(`[Skipped file "${file.name}": unsupported type ${file.mimetype}]`);
        }
      } catch (err) {
        parts.push(`[Failed to download "${file.name}": ${err instanceof Error ? err.message : String(err)}]`);
      }
    }

    return parts.join("\n\n");
  }
}

function isTextMimetype(mimetype: string): boolean {
  return mimetype.startsWith("text/") || mimetype === "application/json" || mimetype === "application/xml";
}

function isTextExtension(filetype: string): boolean {
  const textTypes = new Set([
    "py", "js", "ts", "tsx", "jsx", "rb", "go", "rs", "java", "kt", "swift",
    "c", "cpp", "h", "hpp", "cs", "css", "html", "xml", "json", "yaml", "yml",
    "md", "txt", "sh", "bash", "zsh", "sql", "diff", "patch", "toml", "ini",
    "cfg", "conf", "env", "csv", "log",
  ]);
  return textTypes.has(filetype);
}

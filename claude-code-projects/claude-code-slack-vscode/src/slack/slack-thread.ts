import { EventEmitter } from "events";
import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import * as os from "os";
import { SlackClient, type SlackIncomingMessage, type SlackFileMetadata } from "./slack-client";
import { markdownToMrkdwn } from "./message-formatter";
import { buildEditDiff, buildWritePreview, inferSnippetType } from "./diff-utils";

const MAX_SLACK_TEXT = 3900;
const MAX_SECTION_TEXT = 3000; // Slack Block Kit section text limit
const DEFAULT_BUFFER_INTERVAL = 1500;
const INBOX_POLL_INTERVAL = 2000;
const HEARTBEAT_INTERVAL = 10000; // 10s

/**
 * Per-session Slack thread manager.
 * Handles buffered outbound posting and inbound message reading from IPC inbox.
 * Registers itself with the daemon by creating a session directory.
 */
export class SlackThread extends EventEmitter {
  private client: SlackClient;
  private threadTs: string | null = null;
  private seenTimestamps = new Set<string>();
  private buffer = "";
  private bufferTimer: ReturnType<typeof setTimeout> | null = null;
  private bufferInterval: number;
  private pendingAckTimestamps: string[] = [];
  private inboxPollTimer: ReturnType<typeof setInterval> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private sessionId: string | null = null;
  private sessionDir: string | null = null;
  /** Maps message ts → requestId for permission messages with buttons */
  private pendingButtonMessages = new Map<string, { type: "permission" | "question"; id: string }>();

  constructor(
    client: SlackClient,
    options?: { bufferInterval?: number }
  ) {
    super();
    this.client = client;
    this.bufferInterval = options?.bufferInterval ?? DEFAULT_BUFFER_INTERVAL;
  }

  get thread_ts(): string | null {
    return this.threadTs;
  }

  /**
   * Start the thread by posting an initial message and registering with the daemon.
   */
  async start(cwd: string): Promise<string | undefined> {
    const hostname = os.hostname();
    const text = `*Claude Code session started*\n\`${hostname}:${cwd}\``;
    const ts = await this.client.postMessage(text);
    if (ts) {
      this.threadTs = ts;
    }

    // Generate session ID and register with daemon
    this.sessionId = crypto.randomBytes(4).toString("hex");
    await this.registerSession(cwd);

    // Start polling inbox for messages from daemon
    this.startInboxPolling();
    this.startHeartbeat();

    return ts;
  }

  /**
   * Post text to the thread with buffering.
   * Text accumulates and flushes every `bufferInterval` ms.
   */
  post(text: string, options?: { emoji?: string; immediate?: boolean }): void {
    if (!this.threadTs) return;

    if (options?.immediate) {
      this.flush();
      this.sendChunked(text).catch(() => {});
      return;
    }

    this.buffer += (this.buffer ? "\n" : "") + text;
    this.scheduleFlush();
  }

  /**
   * Flush any buffered text immediately.
   */
  async flush(): Promise<void> {
    if (this.bufferTimer) {
      clearTimeout(this.bufferTimer);
      this.bufferTimer = null;
    }

    if (!this.buffer.trim() || !this.threadTs) return;

    const text = this.buffer;
    this.buffer = "";
    await this.sendChunked(text);
  }

  /**
   * Post a permission request to Slack as Block Kit buttons.
   * Response comes via daemon-routed block_action → inbox → emit 'permissionResponse'.
   * Text-based approve/deny ("yes"/"no") also works as fallback.
   */
  async postPermissionRequest(
    requestId: string,
    toolName: string,
    inputStr: string,
    toolInput?: unknown
  ): Promise<void> {
    if (!this.threadTs) return;

    // Upload a diff/content snippet before the buttons (fire-and-forget)
    await this.uploadToolDiff(toolName, toolInput);

    const fallbackText = `Claude wants to use ${toolName}: ${inputStr} — Approve? (yes/no)`;
    const blocks = [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*Claude wants to use \`${toolName}\`:*\n${inputStr}`,
        },
      },
      {
        type: "actions",
        block_id: `perm_${this.sessionId}_${requestId}`,
        elements: [
          {
            type: "button",
            text: { type: "plain_text", text: "Approve" },
            action_id: `approve_${requestId}`,
            value: "approve",
            style: "primary",
          },
          {
            type: "button",
            text: { type: "plain_text", text: "Deny" },
            action_id: `deny_${requestId}`,
            value: "deny",
            style: "danger",
          },
        ],
      },
    ];

    const ts = await this.client.postMessage(fallbackText, this.threadTs, blocks);
    if (ts) {
      this.pendingButtonMessages.set(ts, { type: "permission", id: requestId });
    }
  }

  /**
   * Upload a diff/content snippet for Edit or Write tool before posting buttons.
   * Silently catches errors — buttons always post regardless.
   */
  private async uploadToolDiff(
    toolName: string,
    toolInput: unknown
  ): Promise<void> {
    if (!this.threadTs || !toolInput || typeof toolInput !== "object") return;
    const inp = toolInput as Record<string, unknown>;

    try {
      if (toolName === "Edit" && inp.file_path && inp.old_string != null && inp.new_string != null) {
        const diff = buildEditDiff({
          file_path: String(inp.file_path),
          old_string: String(inp.old_string),
          new_string: String(inp.new_string),
        });
        const baseName = path.basename(String(inp.file_path));
        await this.client.uploadFileContent(diff, {
          threadTs: this.threadTs,
          filename: `edit-${baseName}.diff`,
          snippetType: "diff",
        });
      } else if (toolName === "Write" && inp.file_path && inp.content != null) {
        const preview = buildWritePreview({
          file_path: String(inp.file_path),
          content: String(inp.content),
        });
        const baseName = path.basename(String(inp.file_path));
        await this.client.uploadFileContent(preview, {
          threadTs: this.threadTs,
          filename: baseName,
          snippetType: inferSnippetType(String(inp.file_path)),
        });
      }
    } catch {
      // Silently ignore — buttons should always post
    }
  }

  /**
   * Post a question (AskUserQuestion) to Slack as Block Kit buttons.
   * Response comes via daemon-routed block_action → inbox → emit 'questionResponse'.
   */
  async postQuestion(
    questionId: string,
    question: string,
    options: { label: string; description?: string }[]
  ): Promise<void> {
    if (!this.threadTs) return;

    const fallbackText = `${question} — ${options.map((o) => o.label).join(" / ")} (or type your answer)`;
    const blocks: any[] = [
      {
        type: "section",
        text: { type: "mrkdwn", text: `*${question}*` },
      },
      {
        type: "actions",
        block_id: `q_${this.sessionId}_${questionId}`,
        elements: options.map((opt, i) => ({
          type: "button",
          text: { type: "plain_text", text: opt.label.slice(0, 75) },
          action_id: `answer_${questionId}_${i}`,
          value: opt.label,
        })),
      },
      {
        type: "actions",
        block_id: `qt_${this.sessionId}_${questionId}`,
        elements: [
          {
            type: "plain_text_input",
            action_id: `answer_text_${questionId}`,
            placeholder: {
              type: "plain_text",
              text: "Or type a custom answer and press Enter…",
            },
            dispatch_action_config: {
              trigger_actions_on: ["on_enter_pressed"],
            },
          },
        ],
      },
    ];

    const ts = await this.client.postMessage(fallbackText, this.threadTs, blocks);
    if (ts) {
      this.pendingButtonMessages.set(ts, { type: "question", id: questionId });
    }
  }

  /**
   * Acknowledge processed messages: swap 👀 → ✅
   */
  async ackMessages(): Promise<void> {
    const timestamps = [...this.pendingAckTimestamps];
    this.pendingAckTimestamps = [];

    for (const ts of timestamps) {
      await this.client.removeReaction("eyes", ts);
      await this.client.addReaction("white_check_mark", ts);
    }
  }

  /**
   * Post session end message and clean up.
   */
  async end(): Promise<void> {
    await this.flush();

    if (this.threadTs) {
      await this.client.postMessage("_Session ended_", this.threadTs);
    }

    this.stopInboxPolling();
    this.stopHeartbeat();
    this.cleanupSession();

    this.seenTimestamps.clear();
    this.pendingAckTimestamps = [];
    this.pendingButtonMessages.clear();
  }

  // ---------------------------------------------------------------------------
  // Session registration (IPC)
  // ---------------------------------------------------------------------------

  private async registerSession(cwd: string): Promise<void> {
    if (!this.sessionId || !this.threadTs) return;

    const ipcBase = path.join(os.homedir(), ".claude", "ipc", "slack", "sessions", this.sessionId);
    this.sessionDir = ipcBase;

    const inboxDir = path.join(ipcBase, "inbox");
    fs.mkdirSync(inboxDir, { recursive: true });

    const sessionData = {
      channel: this.client.channelId,
      thread_ts: this.threadTs,
      session_id: this.sessionId,
      cwd,
      started_at: Date.now() / 1000,
    };

    const sessionFile = path.join(ipcBase, "session.json");
    fs.writeFileSync(sessionFile, JSON.stringify(sessionData), "utf-8");

    this.emit("debug", `Session registered: ${this.sessionId} → ${this.threadTs}`);
  }

  private cleanupSession(): void {
    if (!this.sessionDir) return;

    try {
      // Remove inbox files
      const inboxDir = path.join(this.sessionDir, "inbox");
      if (fs.existsSync(inboxDir)) {
        for (const f of fs.readdirSync(inboxDir)) {
          try { fs.unlinkSync(path.join(inboxDir, f)); } catch {}
        }
        try { fs.rmdirSync(inboxDir); } catch {}
      }
      // Remove session.json, heartbeat, daemon.log
      try { fs.unlinkSync(path.join(this.sessionDir, "session.json")); } catch {}
      try { fs.unlinkSync(path.join(this.sessionDir, "heartbeat")); } catch {}
      try { fs.unlinkSync(path.join(this.sessionDir, "daemon.log")); } catch {}
      // Remove session dir
      try { fs.rmdirSync(this.sessionDir); } catch {}
    } catch {
      // Best-effort cleanup
    }

    this.emit("debug", `Session cleaned up: ${this.sessionId}`);
    this.sessionDir = null;
  }

  // ---------------------------------------------------------------------------
  // Heartbeat — daemon uses this to detect dead sessions
  // ---------------------------------------------------------------------------

  private startHeartbeat(): void {
    if (!this.sessionDir) return;
    this.writeHeartbeat();
    this.heartbeatTimer = setInterval(() => this.writeHeartbeat(), HEARTBEAT_INTERVAL);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private writeHeartbeat(): void {
    if (!this.sessionDir) return;
    try {
      const hbFile = path.join(this.sessionDir, "heartbeat");
      fs.writeFileSync(hbFile, String(Date.now()), "utf-8");
    } catch {
      // Best-effort
    }
  }

  // ---------------------------------------------------------------------------
  // Inbox polling (reads messages AND block_actions from daemon)
  // ---------------------------------------------------------------------------

  private startInboxPolling(): void {
    if (!this.sessionDir) return;

    const inboxDir = path.join(this.sessionDir, "inbox");

    this.inboxPollTimer = setInterval(() => {
      try {
        if (!fs.existsSync(inboxDir)) return;

        const files = fs.readdirSync(inboxDir)
          .filter((f) => f.endsWith(".json"))
          .sort();

        for (const file of files) {
          const filePath = path.join(inboxDir, file);
          try {
            const raw = fs.readFileSync(filePath, "utf-8");
            // Consume (delete) BEFORE processing to avoid double-reads
            fs.unlinkSync(filePath);

            const data = JSON.parse(raw);

            if (data.type === "block_action") {
              this.handleBlockAction(data);
            } else {
              // Regular message
              const msg: SlackIncomingMessage = {
                text: data.text ?? "",
                user: data.user ?? "",
                ts: data.ts ?? "",
                channel: this.client.channelId ?? "",
                threadTs: this.threadTs ?? undefined,
                files: data.files ?? undefined,
              };
              this.handleIncoming(msg);
            }
          } catch {
            // Skip malformed files; already deleted if possible
          }
        }
      } catch {
        // Inbox dir may not exist yet
      }
    }, INBOX_POLL_INTERVAL);
  }

  private stopInboxPolling(): void {
    if (this.inboxPollTimer) {
      clearInterval(this.inboxPollTimer);
      this.inboxPollTimer = null;
    }
  }

  // ---------------------------------------------------------------------------
  // Inbound message handling
  // ---------------------------------------------------------------------------

  private handleIncoming(msg: SlackIncomingMessage): void {
    this.emit("debug", `handleIncoming: text="${msg.text.slice(0, 50)}" ts=${msg.ts}`);

    // Dedup
    if (this.seenTimestamps.has(msg.ts)) return;
    this.seenTimestamps.add(msg.ts);

    // Track for ack (daemon already added 👀, we'll swap to ✅)
    this.pendingAckTimestamps.push(msg.ts);

    // Check for permission responses (text-based fallback)
    const lower = msg.text.toLowerCase().trim();
    const approvePatterns = [
      "yes", "y", "approve", "ok", "go", "lgtm", "do it",
      "proceed", "looks good", "sure", "yep", "yup",
      "absolutely", "confirmed", "accepted", "ack", "+1", "ship it",
    ];

    if (approvePatterns.includes(lower)) {
      this.emit("permissionResponse", { approved: true, text: msg.text });
      return;
    }

    const denyPatterns = ["no", "n", "deny", "reject", "stop", "cancel"];
    if (denyPatterns.includes(lower)) {
      this.emit("permissionResponse", { approved: false, text: msg.text });
      return;
    }

    // Regular user reply
    this.emit("userReply", msg.text, msg.files);
  }

  // ---------------------------------------------------------------------------
  // Block action handling (button clicks routed through daemon)
  // ---------------------------------------------------------------------------

  private handleBlockAction(data: any): void {
    const actionId: string = data.action_id ?? "";
    const value: string = data.value ?? "";
    const messageTs: string = data.message_ts ?? "";

    this.emit("debug", `handleBlockAction: action_id=${actionId} value=${value}`);

    // Permission button: approve_<requestId> or deny_<requestId>
    const approveMatch = actionId.match(/^approve_(.+)$/);
    if (approveMatch) {
      this.emit("permissionResponse", { approved: true, text: "Approved (button)" });
      this.updateButtonMessage(messageTs, "\u2705 Approved by user");
      this.pendingButtonMessages.delete(messageTs);
      return;
    }

    const denyMatch = actionId.match(/^deny_(.+)$/);
    if (denyMatch) {
      this.emit("permissionResponse", { approved: false, text: "Denied (button)" });
      this.updateButtonMessage(messageTs, "\u274c Denied by user");
      this.pendingButtonMessages.delete(messageTs);
      return;
    }

    // Question text input: answer_text_<questionId>
    const answerTextMatch = actionId.match(/^answer_text_(.+)$/);
    if (answerTextMatch) {
      const [, questionId] = answerTextMatch;
      this.emit("questionResponse", { questionId, answer: value });
      this.updateButtonMessage(messageTs, `Answered: "${value}"`);
      this.pendingButtonMessages.delete(messageTs);
      return;
    }

    // Question button: answer_<questionId>_<index>
    const answerMatch = actionId.match(/^answer_(.+?)_(\d+)$/);
    if (answerMatch) {
      const [, questionId] = answerMatch;
      this.emit("questionResponse", { questionId, answer: value });
      this.updateButtonMessage(messageTs, `Selected: "${value}"`);
      this.pendingButtonMessages.delete(messageTs);
      return;
    }
  }

  private updateButtonMessage(messageTs: string, resultText: string): void {
    const blocks = [
      {
        type: "section",
        text: { type: "mrkdwn", text: resultText },
      },
    ];
    this.client.updateMessage(messageTs, resultText, blocks).catch(() => {});
  }

  private scheduleFlush(): void {
    if (this.bufferTimer) return;
    this.bufferTimer = setTimeout(() => {
      this.bufferTimer = null;
      this.flush().catch(() => {});
    }, this.bufferInterval);
  }

  private async sendChunked(text: string): Promise<void> {
    if (!this.threadTs) return;

    const mrkdwn = markdownToMrkdwn(text);

    // Split into section-sized chunks (3000 char limit per section block)
    const sectionChunks = chunkText(mrkdwn, MAX_SECTION_TEXT);

    // Slack allows max 50 blocks per message
    for (let i = 0; i < sectionChunks.length; i += 50) {
      const batch = sectionChunks.slice(i, i + 50);
      const blocks = batch.map((chunk) => ({
        type: "section",
        text: { type: "mrkdwn", text: chunk },
      }));
      const fallback = batch.join("\n");
      await this.client.postMessage(fallback, this.threadTs, blocks);
    }
  }
}

function chunkText(text: string, maxLen: number): string[] {
  if (text.length <= maxLen) return [text];

  const chunks: string[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    if (remaining.length <= maxLen) {
      chunks.push(remaining);
      break;
    }

    // Try to break at a newline
    let breakPoint = remaining.lastIndexOf("\n", maxLen);
    if (breakPoint < maxLen * 0.5) {
      // No good newline break, try space
      breakPoint = remaining.lastIndexOf(" ", maxLen);
    }
    if (breakPoint < maxLen * 0.3) {
      // No good break at all, hard break
      breakPoint = maxLen;
    }

    chunks.push(remaining.slice(0, breakPoint));
    remaining = remaining.slice(breakPoint).trimStart();
  }

  return chunks;
}

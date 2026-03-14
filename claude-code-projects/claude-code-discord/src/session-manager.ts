import type { ThreadChannel } from "discord.js";
import { SDKClient, type SDKClientOptions } from "./sdk-client.js";
import { DiscordThread } from "./discord-thread.js";
import { MessageRouter, type MessageSink } from "./message-router.js";
import type {
  Session,
  SessionInfo,
  PendingQuestion,
  DiscordAttachment,
} from "./types.js";
import type { Config } from "./config.js";

/**
 * Multi-session manager. Each Discord thread = independent session.
 */
export class SessionManager {
  private sessions = new Map<string, Session>();
  private sessionIdIndex = new Map<string, string>(); // sdkSessionId -> threadId
  private pendingQuestions = new Map<string, PendingQuestion>();
  private config: Config;

  constructor(config: Config) {
    this.config = config;
  }

  get sessionCount(): number {
    return this.sessions.size;
  }

  hasSession(threadId: string): boolean {
    return this.sessions.has(threadId);
  }

  /**
   * Create a new session for a Discord thread.
   */
  async createSession(
    thread: ThreadChannel,
    cwd: string,
    prompt: string,
    attachments?: DiscordAttachment[]
  ): Promise<void> {
    if (this.sessions.size >= this.config.maxConcurrentSessions) {
      await thread.send(
        `**Error:** Maximum concurrent sessions (${this.config.maxConcurrentSessions}) reached. Stop an existing session first.`
      );
      return;
    }

    const sdkClient = new SDKClient();
    const discordThread = new DiscordThread(thread, {
      bufferInterval: this.config.bufferIntervalMs,
    });

    const sink: MessageSink = {
      postText: (text) => discordThread.post(text),
      postToolUse: (toolName, inputStr) =>
        discordThread.post(`\`${toolName}\`: ${inputStr}`),
      postPermissionRequest: (requestId, toolName, inputStr, toolInput) =>
        discordThread.postPermissionRequest(requestId, toolName, inputStr, toolInput),
      postQuestion: (questionId, question, options) =>
        discordThread.postQuestion(questionId, question, options),
      postResult: (text) => discordThread.postResult(text),
      postSessionInfo: (info) => discordThread.postSessionInfo(info),
    };

    const router = new MessageRouter(sink);

    const session: Session = {
      threadId: thread.id,
      cwd,
      sdkClient,
      discordThread,
      router,
      info: null,
      lastActivity: Date.now(),
      timeoutTimer: null,
    };

    this.sessions.set(thread.id, session);
    this.setupListeners(session);
    this.resetTimeout(session);

    const options: SDKClientOptions = {
      model: this.config.model,
      cwd,
      permissionMode: this.config.permissionMode,
      systemPrompt: this.config.systemPrompt,
    };

    await sdkClient.sendMessage(prompt, options, attachments);
  }

  /**
   * Handle a follow-up message in an existing session thread.
   */
  async handleFollowUp(
    threadId: string,
    text: string,
    attachments?: DiscordAttachment[]
  ): Promise<void> {
    const session = this.sessions.get(threadId);
    if (!session) return;

    session.lastActivity = Date.now();
    this.resetTimeout(session);

    const options: SDKClientOptions = {
      model: this.config.model,
      cwd: session.cwd,
      permissionMode: this.config.permissionMode,
      systemPrompt: this.config.systemPrompt,
      resume: session.sdkClient.currentSessionId ?? undefined,
    };

    await session.sdkClient.sendMessage(text, options, attachments);
  }

  /**
   * Resume a session by SDK session ID in a new thread.
   */
  async resumeSession(
    thread: ThreadChannel,
    sdkSessionId: string
  ): Promise<boolean> {
    // Find the original session to get cwd
    const originalThreadId = this.sessionIdIndex.get(sdkSessionId);
    const originalSession = originalThreadId
      ? this.sessions.get(originalThreadId)
      : undefined;
    const cwd = originalSession?.cwd ?? process.cwd();

    if (this.sessions.size >= this.config.maxConcurrentSessions) {
      await thread.send(
        `**Error:** Maximum concurrent sessions (${this.config.maxConcurrentSessions}) reached.`
      );
      return false;
    }

    const sdkClient = new SDKClient();
    const discordThread = new DiscordThread(thread, {
      bufferInterval: this.config.bufferIntervalMs,
    });

    const sink: MessageSink = {
      postText: (text) => discordThread.post(text),
      postToolUse: (toolName, inputStr) =>
        discordThread.post(`\`${toolName}\`: ${inputStr}`),
      postPermissionRequest: (requestId, toolName, inputStr, toolInput) =>
        discordThread.postPermissionRequest(requestId, toolName, inputStr, toolInput),
      postQuestion: (questionId, question, options) =>
        discordThread.postQuestion(questionId, question, options),
      postResult: (text) => discordThread.postResult(text),
      postSessionInfo: (info) => discordThread.postSessionInfo(info),
    };

    const router = new MessageRouter(sink);

    const session: Session = {
      threadId: thread.id,
      cwd,
      sdkClient,
      discordThread,
      router,
      info: null,
      lastActivity: Date.now(),
      timeoutTimer: null,
    };

    this.sessions.set(thread.id, session);
    this.setupListeners(session);
    this.resetTimeout(session);

    await thread.send(`**Resuming session** \`${sdkSessionId}\`...`);

    const options: SDKClientOptions = {
      model: this.config.model,
      cwd,
      permissionMode: this.config.permissionMode,
      systemPrompt: this.config.systemPrompt,
      resume: sdkSessionId,
    };

    await sdkClient.sendMessage("Continue from where we left off.", options);
    return true;
  }

  /**
   * Handle permission response (button click).
   */
  handlePermissionResponse(requestId: string, approved: boolean): void {
    // Find which session owns this permission
    for (const session of this.sessions.values()) {
      session.sdkClient.resolvePermission(requestId, approved);
    }
  }

  /**
   * Handle question response (button click or modal).
   */
  handleQuestionResponse(questionId: string, answer: string): void {
    const pending = this.pendingQuestions.get(questionId);
    if (!pending) return;

    this.pendingQuestions.delete(questionId);

    const session = this.sessions.get(pending.threadId);
    if (!session) return;

    // Build updatedInput with the answer injected
    const input = (pending.toolInput ?? {}) as Record<string, unknown>;
    const updatedInput = {
      ...input,
      answers: { [pending.question]: answer },
    };

    session.sdkClient.resolvePermissionWithInput(pending.permissionId, updatedInput);
  }

  /**
   * Stop a session.
   */
  async stopSession(threadId: string): Promise<void> {
    const session = this.sessions.get(threadId);
    if (!session) return;

    await session.sdkClient.stop();
    await session.discordThread.flush();
    session.discordThread.post("*Session stopped.*", { immediate: true });

    this.destroySession(threadId);
  }

  /**
   * Get session status.
   */
  getSessionStatus(threadId: string): string | null {
    const session = this.sessions.get(threadId);
    if (!session) return null;

    const running = session.sdkClient.isRunning ? "running" : "idle";
    const sessionId = session.info?.sessionId ?? "unknown";
    const model = session.info?.model ?? this.config.model;
    const elapsed = Math.round((Date.now() - (session.info?.startedAt ?? Date.now())) / 1000);

    return [
      `**Status:** ${running}`,
      `**Session ID:** \`${sessionId}\``,
      `**Model:** \`${model}\``,
      `**CWD:** \`${session.cwd}\``,
      `**Uptime:** ${elapsed}s`,
    ].join("\n");
  }

  /**
   * Stop all sessions (for graceful shutdown).
   */
  async stopAll(): Promise<void> {
    const promises = Array.from(this.sessions.keys()).map((id) =>
      this.stopSession(id)
    );
    await Promise.allSettled(promises);
  }

  private destroySession(threadId: string): void {
    const session = this.sessions.get(threadId);
    if (!session) return;

    if (session.timeoutTimer) {
      clearTimeout(session.timeoutTimer);
    }

    // Remove session ID index entries
    if (session.info?.sessionId) {
      this.sessionIdIndex.delete(session.info.sessionId);
    }

    // Clean up pending questions for this session
    for (const [qId, pq] of this.pendingQuestions) {
      if (pq.threadId === threadId) {
        this.pendingQuestions.delete(qId);
      }
    }

    this.sessions.delete(threadId);
    console.log(`[SessionManager] Destroyed session for thread ${threadId}`);
  }

  private resetTimeout(session: Session): void {
    if (session.timeoutTimer) {
      clearTimeout(session.timeoutTimer);
    }

    session.timeoutTimer = setTimeout(() => {
      console.log(`[SessionManager] Session timeout for thread ${session.threadId}`);
      session.discordThread.post("*Session timed out after inactivity.*", {
        immediate: true,
      });
      this.destroySession(session.threadId);
    }, this.config.sessionTimeoutMs);
  }

  private setupListeners(session: Session): void {
    const { sdkClient, router, threadId } = session;

    sdkClient.on("message", (message) => {
      session.lastActivity = Date.now();
      router.routeMessage(message);
    });

    sdkClient.on("sessionInit", (info: SessionInfo) => {
      session.info = { ...info, threadId };
      this.sessionIdIndex.set(info.sessionId, threadId);
      router.routeSessionInfo(info);
    });

    sdkClient.on("permissionRequest", (request) => {
      session.lastActivity = Date.now();

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
            threadId,
          });
          router.routeQuestion(questionId, q.question, q.options ?? []);
          return;
        }
      }

      router.routePermissionRequest(request.id, request.toolName, request.toolInput);
    });

    sdkClient.on("notification", ({ title, message }: { title: string; message: string }) => {
      router.routeNotification(title, message);
    });

    sdkClient.on("error", (err: Error) => {
      const errorMsg = err instanceof Error ? err.message : "Unknown error";
      session.discordThread.post(`**Error:** ${errorMsg}`, { immediate: true });
    });

    sdkClient.on("turnComplete", () => {
      session.lastActivity = Date.now();
      this.resetTimeout(session);
    });
  }
}

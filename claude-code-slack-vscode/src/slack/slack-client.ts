import { EventEmitter } from "events";
import { WebClient } from "@slack/web-api";

export interface SlackClientOptions {
  botToken: string;
  userId: string;
}

export interface SlackFileMetadata {
  id: string;
  name: string;
  mimetype: string;
  filetype: string;
  size: number;
  url_private_download: string;
}

export interface SlackIncomingMessage {
  text: string;
  user: string;
  ts: string;
  channel: string;
  threadTs?: string;
  files?: SlackFileMetadata[];
}

/**
 * Slack Web API client for posting messages.
 * Inbound messages are handled via IPC inbox (daemon routes them).
 */
export class SlackClient extends EventEmitter {
  private web: WebClient;
  private userId: string;
  private botToken: string;
  private dmChannelId: string | null = null;
  private _connected = false;

  constructor(options: SlackClientOptions) {
    super();
    this.userId = options.userId;
    this.botToken = options.botToken;
    this.web = new WebClient(options.botToken);
  }

  get connected(): boolean {
    return this._connected;
  }

  get webClient(): WebClient {
    return this.web;
  }

  get channelId(): string | null {
    return this.dmChannelId;
  }

  /**
   * Connect to Slack: open DM channel and verify bot token works.
   */
  async connect(): Promise<void> {
    try {
      // Open DM channel with configured user
      const result = await this.web.conversations.open({
        users: this.userId,
      });
      this.dmChannelId = (result.channel as any)?.id ?? null;

      if (!this.dmChannelId) {
        throw new Error("Failed to open DM channel");
      }

      this._connected = true;
      this.emit("connected");
    } catch (err) {
      this._connected = false;
      this.emit("error", err);
      throw err;
    }
  }

  /**
   * Post a message to a thread, optionally with Block Kit blocks.
   */
  async postMessage(
    text: string,
    threadTs?: string,
    blocks?: any[]
  ): Promise<string | undefined> {
    if (!this.dmChannelId) return undefined;

    try {
      const result = await this.web.chat.postMessage({
        channel: this.dmChannelId,
        text,
        thread_ts: threadTs,
        blocks,
        unfurl_links: false,
        unfurl_media: false,
      });
      return result.ts;
    } catch (err) {
      this.emit("error", err);
      return undefined;
    }
  }

  /**
   * Update an existing message (e.g. replace buttons with confirmation text).
   */
  async updateMessage(
    ts: string,
    text: string,
    blocks?: any[]
  ): Promise<void> {
    if (!this.dmChannelId) return;

    try {
      await this.web.chat.update({
        channel: this.dmChannelId,
        ts,
        text,
        blocks,
      });
    } catch (err) {
      this.emit("error", err);
    }
  }

  /**
   * Add a reaction to a message.
   */
  async addReaction(
    name: string,
    messageTs: string,
    channel?: string
  ): Promise<void> {
    try {
      await this.web.reactions.add({
        channel: channel ?? this.dmChannelId!,
        timestamp: messageTs,
        name,
      });
    } catch {
      // Reaction already exists or other non-critical error
    }
  }

  /**
   * Remove a reaction from a message.
   */
  async removeReaction(
    name: string,
    messageTs: string,
    channel?: string
  ): Promise<void> {
    try {
      await this.web.reactions.remove({
        channel: channel ?? this.dmChannelId!,
        timestamp: messageTs,
        name,
      });
    } catch {
      // Reaction doesn't exist or other non-critical error
    }
  }

  /**
   * Upload a text snippet to a thread via filesUploadV2.
   * Returns the file ID on success, undefined on failure.
   */
  async uploadFileContent(
    content: string,
    options: {
      threadTs: string;
      filename: string;
      snippetType?: string;
    }
  ): Promise<string | undefined> {
    if (!this.dmChannelId) return undefined;

    try {
      const result = await this.web.filesUploadV2({
        channel_id: this.dmChannelId,
        thread_ts: options.threadTs,
        content,
        filename: options.filename,
        snippet_type: options.snippetType,
      });
      return (result as any).files?.[0]?.id ?? (result as any).file?.id;
    } catch (err) {
      this.emit("error", err);
      return undefined;
    }
  }

  /**
   * Download a file from Slack using the bot token for auth.
   */
  async downloadFile(url: string): Promise<Buffer> {
    const resp = await fetch(url, {
      headers: { Authorization: `Bearer ${this.botToken}` },
    });
    if (!resp.ok) {
      throw new Error(`Slack file download failed: ${resp.status} ${resp.statusText}`);
    }
    const arrayBuf = await resp.arrayBuffer();
    return Buffer.from(arrayBuf);
  }

  /**
   * Disconnect from Slack.
   */
  async disconnect(): Promise<void> {
    this._connected = false;
    this.emit("disconnected");
  }
}

import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  type ThreadChannel,
  type ButtonInteraction,
  type ModalSubmitInteraction,
} from "discord.js";
import type { SessionInfo } from "./types.js";

const MAX_DISCORD_MSG = 1950; // Leave 50 chars headroom from 2000 limit
const DEFAULT_BUFFER_INTERVAL = 1500;

/**
 * Per-session Discord thread handler.
 * Manages buffered posting, chunking, permission buttons, and question buttons.
 */
export class DiscordThread {
  private thread: ThreadChannel;
  private buffer = "";
  private bufferTimer: ReturnType<typeof setTimeout> | null = null;
  private bufferInterval: number;

  constructor(thread: ThreadChannel, options?: { bufferInterval?: number }) {
    this.thread = thread;
    this.bufferInterval = options?.bufferInterval ?? DEFAULT_BUFFER_INTERVAL;
  }

  /**
   * Post text to the thread with buffering.
   */
  post(text: string, options?: { immediate?: boolean }): void {
    if (options?.immediate) {
      this.flush();
      this.sendChunked(text).catch((err) =>
        console.error("[DiscordThread] sendChunked error:", err)
      );
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

    if (!this.buffer.trim()) return;

    const text = this.buffer;
    this.buffer = "";
    await this.sendChunked(text);
  }

  /**
   * Post a permission request with Approve/Deny buttons.
   */
  async postPermissionRequest(
    requestId: string,
    toolName: string,
    inputStr: string,
    toolInput?: unknown
  ): Promise<void> {
    await this.flush();

    // Build diff/preview for Edit/Write tools
    let diffPreview = "";
    if (toolInput && typeof toolInput === "object") {
      const inp = toolInput as Record<string, unknown>;
      if (toolName === "Edit" && inp.old_string != null && inp.new_string != null) {
        diffPreview = buildEditDiff(
          String(inp.file_path ?? ""),
          String(inp.old_string),
          String(inp.new_string)
        );
      } else if (toolName === "Write" && inp.content != null) {
        const content = String(inp.content);
        const preview = content.length > 4000 ? content.slice(0, 4000) + "\n... (truncated)" : content;
        const ext = String(inp.file_path ?? "").split(".").pop() ?? "";
        diffPreview = `\`\`\`${ext}\n${preview}\n\`\`\``;
      }
    }

    const header = `**Claude wants to use \`${toolName}\`:**\n${inputStr}`;

    // Post diff preview if present (separate message to stay under limits)
    if (diffPreview) {
      const chunks = chunkText(diffPreview, MAX_DISCORD_MSG);
      for (const chunk of chunks) {
        await this.thread.send(chunk).catch(() => {});
      }
    }

    const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`approve:${requestId}`)
        .setLabel("Approve")
        .setStyle(ButtonStyle.Success),
      new ButtonBuilder()
        .setCustomId(`deny:${requestId}`)
        .setLabel("Deny")
        .setStyle(ButtonStyle.Danger)
    );

    // Truncate header if needed
    const msgText = header.length > MAX_DISCORD_MSG ? header.slice(0, MAX_DISCORD_MSG) : header;
    await this.thread.send({ content: msgText, components: [row] });
  }

  /**
   * Post a question with option buttons.
   */
  async postQuestion(
    questionId: string,
    question: string,
    options: { label: string; description?: string }[]
  ): Promise<void> {
    await this.flush();

    const rows: ActionRowBuilder<ButtonBuilder>[] = [];

    // Option buttons (up to 5 per row, max 5 rows = 25 buttons)
    for (let i = 0; i < options.length && rows.length < 4; i += 5) {
      const batch = options.slice(i, i + 5);
      const row = new ActionRowBuilder<ButtonBuilder>().addComponents(
        ...batch.map((opt, j) =>
          new ButtonBuilder()
            .setCustomId(`answer:${questionId}:${i + j}`)
            .setLabel(opt.label.slice(0, 80))
            .setStyle(ButtonStyle.Primary)
        )
      );
      rows.push(row);
    }

    // "Type answer..." button that opens a modal
    const modalRow = new ActionRowBuilder<ButtonBuilder>().addComponents(
      new ButtonBuilder()
        .setCustomId(`modal:${questionId}`)
        .setLabel("Type answer...")
        .setStyle(ButtonStyle.Secondary)
    );
    rows.push(modalRow);

    const msgText = `**${question}**`;
    await this.thread.send({
      content: msgText.slice(0, MAX_DISCORD_MSG),
      components: rows,
    });
  }

  /**
   * Post session info.
   */
  async postSessionInfo(info: SessionInfo): Promise<void> {
    const text = [
      `**Session started**`,
      `> Model: \`${info.model}\``,
      `> CWD: \`${info.cwd}\``,
      `> Session ID: \`${info.sessionId}\``,
    ].join("\n");

    this.post(text, { immediate: true });
  }

  /**
   * Post result summary.
   */
  async postResult(text: string): Promise<void> {
    this.post(text, { immediate: true });
  }

  /**
   * Handle button interaction result — update the original message.
   */
  static async updateButtonResult(
    interaction: ButtonInteraction,
    resultText: string
  ): Promise<void> {
    await interaction.update({ content: resultText, components: [] });
  }

  /**
   * Build a modal for custom text answer.
   */
  static buildAnswerModal(questionId: string): ModalBuilder {
    const modal = new ModalBuilder()
      .setCustomId(`modal_answer:${questionId}`)
      .setTitle("Your Answer");

    const input = new TextInputBuilder()
      .setCustomId("answer_text")
      .setLabel("Type your answer")
      .setStyle(TextInputStyle.Paragraph)
      .setRequired(true);

    const row = new ActionRowBuilder<TextInputBuilder>().addComponents(input);
    modal.addComponents(row);

    return modal;
  }

  /**
   * Cleanup — flush remaining buffer.
   */
  async cleanup(): Promise<void> {
    await this.flush();
  }

  // ---- Internal ----

  private scheduleFlush(): void {
    if (this.bufferTimer) return;
    this.bufferTimer = setTimeout(() => {
      this.bufferTimer = null;
      this.flush().catch((err) =>
        console.error("[DiscordThread] flush error:", err)
      );
    }, this.bufferInterval);
  }

  private async sendChunked(text: string): Promise<void> {
    const chunks = chunkText(text, MAX_DISCORD_MSG);
    for (const chunk of chunks) {
      if (chunk.trim()) {
        await this.thread.send(chunk);
      }
    }
  }
}

/**
 * Split text into chunks respecting Discord's 2000 char limit.
 * Code-block-aware: tracks open ``` markers and closes/reopens across chunks.
 */
function chunkText(text: string, maxLen: number): string[] {
  if (text.length <= maxLen) return [text];

  const chunks: string[] = [];
  let remaining = text;
  let inCodeBlock = false;
  let codeBlockLang = "";

  while (remaining.length > 0) {
    if (remaining.length <= maxLen) {
      chunks.push(remaining);
      break;
    }

    // Reserve space for code block closing/opening markers
    const effectiveMax = inCodeBlock ? maxLen - 10 : maxLen;

    // Try to break at a newline
    let breakPoint = remaining.lastIndexOf("\n", effectiveMax);
    if (breakPoint < effectiveMax * 0.5) {
      breakPoint = remaining.lastIndexOf(" ", effectiveMax);
    }
    if (breakPoint < effectiveMax * 0.3) {
      breakPoint = effectiveMax;
    }

    let chunk = remaining.slice(0, breakPoint);
    remaining = remaining.slice(breakPoint).trimStart();

    // Track code block state
    const backtickMatches = chunk.match(/```/g);
    if (backtickMatches) {
      for (const _match of backtickMatches) {
        if (inCodeBlock) {
          inCodeBlock = false;
          codeBlockLang = "";
        } else {
          inCodeBlock = true;
          // Try to capture language from the opening marker
          const langMatch = chunk.match(/```(\w*)/);
          codeBlockLang = langMatch?.[1] ?? "";
        }
      }
    }

    // If we're inside a code block, close it at end of chunk and reopen in next
    if (inCodeBlock) {
      chunk += "\n```";
      remaining = "```" + codeBlockLang + "\n" + remaining;
    }

    chunks.push(chunk);
  }

  return chunks;
}

function buildEditDiff(filePath: string, oldStr: string, newStr: string): string {
  const oldLines = oldStr.split("\n");
  const newLines = newStr.split("\n");
  const lines: string[] = [`--- ${filePath}`, `+++ ${filePath}`];

  for (const line of oldLines) {
    lines.push(`- ${line}`);
  }
  for (const line of newLines) {
    lines.push(`+ ${line}`);
  }

  const diff = lines.join("\n");
  return `\`\`\`diff\n${diff.length > 3800 ? diff.slice(0, 3800) + "\n... (truncated)" : diff}\n\`\`\``;
}

import {
  Client,
  GatewayIntentBits,
  Events,
  ChannelType,
  type Message,
  type Interaction,
  type ThreadChannel,
} from "discord.js";
import { loadConfig } from "./config.js";
import { SessionManager } from "./session-manager.js";
import { DiscordThread } from "./discord-thread.js";
import type { DiscordAttachment } from "./types.js";

const config = loadConfig();

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

const sessionManager = new SessionManager(config);

// ---- Event: Ready ----

client.once(Events.ClientReady, (c) => {
  console.log(`[Discord] Logged in as ${c.user.tag}`);
  console.log(`[Discord] Watching channel: ${config.channelId}`);
  console.log(`[Discord] Model: ${config.model}, Permission mode: ${config.permissionMode}`);
});

// ---- Event: Message Create ----

client.on(Events.MessageCreate, async (message: Message) => {
  // Ignore bots
  if (message.author.bot) return;

  const channelId = message.channel.isThread()
    ? message.channel.parentId
    : message.channelId;

  // Only respond in the configured channel (or threads under it)
  if (channelId !== config.channelId) return;

  // Message in a thread — handle as follow-up or command
  if (message.channel.isThread()) {
    await handleThreadMessage(message);
    return;
  }

  // Message in the main channel — create a new session
  await handleNewSession(message);
});

// ---- Event: Interaction Create (buttons, modals) ----

client.on(Events.InteractionCreate, async (interaction: Interaction) => {
  // Button interaction
  if (interaction.isButton()) {
    const customId = interaction.customId;

    // Permission: approve:<requestId> or deny:<requestId>
    const approveMatch = customId.match(/^approve:(.+)$/);
    if (approveMatch) {
      const requestId = approveMatch[1];
      sessionManager.handlePermissionResponse(requestId, true);
      await DiscordThread.updateButtonResult(interaction, "\u2705 **Approved**");
      return;
    }

    const denyMatch = customId.match(/^deny:(.+)$/);
    if (denyMatch) {
      const requestId = denyMatch[1];
      sessionManager.handlePermissionResponse(requestId, false);
      await DiscordThread.updateButtonResult(interaction, "\u274c **Denied**");
      return;
    }

    // Question answer: answer:<questionId>:<index>
    const answerMatch = customId.match(/^answer:(.+?):(\d+)$/);
    if (answerMatch) {
      const questionId = answerMatch[1];
      // The button label is the answer value
      const label = "label" in interaction.component ? (interaction.component.label ?? "") : "";
      sessionManager.handleQuestionResponse(questionId, label);
      await DiscordThread.updateButtonResult(
        interaction,
        `**Selected:** "${label}"`
      );
      return;
    }

    // Modal trigger: modal:<questionId>
    const modalMatch = customId.match(/^modal:(.+)$/);
    if (modalMatch) {
      const questionId = modalMatch[1];
      const modal = DiscordThread.buildAnswerModal(questionId);
      await interaction.showModal(modal);
      return;
    }
  }

  // Modal submit
  if (interaction.isModalSubmit()) {
    const customId = interaction.customId;
    const modalMatch = customId.match(/^modal_answer:(.+)$/);
    if (modalMatch) {
      const questionId = modalMatch[1];
      const answer = interaction.fields.getTextInputValue("answer_text");
      sessionManager.handleQuestionResponse(questionId, answer);
      await interaction.reply({ content: `**Answered:** "${answer}"`, ephemeral: true });
      return;
    }
  }
});

// ---- Handlers ----

async function handleNewSession(message: Message): Promise<void> {
  const text = message.content.trim();
  if (!text) return;

  const lines = text.split("\n");
  const firstLine = lines[0].trim();

  // First line must be a directory path (starts with /)
  let cwd: string;
  let prompt: string;

  if (firstLine.startsWith("/")) {
    cwd = firstLine;
    prompt = lines.slice(1).join("\n").trim();
    if (!prompt) {
      prompt = "What would you like me to help with?";
    }
  } else {
    // If no path given, use the first line as prompt with a default cwd
    cwd = process.cwd();
    prompt = text;
  }

  // Create thread from the message
  const threadName = prompt.slice(0, 50) + (prompt.length > 50 ? "..." : "");
  const thread = await message.startThread({
    name: threadName,
    autoArchiveDuration: 1440, // 24 hours
  });

  // Collect attachments
  const attachments = extractAttachments(message);

  console.log(`[Session] New session in thread ${thread.id}: cwd=${cwd}`);
  await sessionManager.createSession(thread, cwd, prompt, attachments);
}

async function handleThreadMessage(message: Message): Promise<void> {
  const thread = message.channel as ThreadChannel;
  const text = message.content.trim();

  // Command: !stop
  if (text === "!stop") {
    await sessionManager.stopSession(thread.id);
    return;
  }

  // Command: !status
  if (text === "!status") {
    const status = sessionManager.getSessionStatus(thread.id);
    if (status) {
      await thread.send(status);
    } else {
      await thread.send("*No active session in this thread.*");
    }
    return;
  }

  // Command: !continue <sessionId>
  const continueMatch = text.match(/^!continue\s+(\S+)/);
  if (continueMatch) {
    const sdkSessionId = continueMatch[1];
    await sessionManager.resumeSession(thread, sdkSessionId);
    return;
  }

  // Regular follow-up message
  if (sessionManager.hasSession(thread.id)) {
    const attachments = extractAttachments(message);
    await sessionManager.handleFollowUp(thread.id, text, attachments);
  }
}

function extractAttachments(message: Message): DiscordAttachment[] | undefined {
  if (message.attachments.size === 0) return undefined;

  return Array.from(message.attachments.values()).map((a) => ({
    name: a.name,
    url: a.url,
    contentType: a.contentType,
    size: a.size,
  }));
}

// ---- Graceful shutdown ----

async function shutdown(signal: string): Promise<void> {
  console.log(`\n[Discord] Received ${signal}, shutting down...`);
  await sessionManager.stopAll();
  client.destroy();
  process.exit(0);
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

// ---- Start ----

client.login(config.discordToken).catch((err) => {
  console.error("[Discord] Failed to login:", err.message);
  process.exit(1);
});

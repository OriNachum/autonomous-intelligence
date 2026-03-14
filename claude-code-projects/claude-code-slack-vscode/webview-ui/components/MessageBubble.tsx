import React, { useMemo } from "react";
import type { ChatMessage } from "../App";

interface MessageBubbleProps {
  message: ChatMessage;
}

const styles: Record<string, React.CSSProperties> = {
  user: {
    background: "var(--vscode-button-background)",
    color: "var(--vscode-button-foreground)",
    padding: "8px 12px",
    borderRadius: "12px 12px 2px 12px",
    alignSelf: "flex-end",
    maxWidth: "85%",
    wordBreak: "break-word",
  },
  assistant: {
    background: "var(--vscode-editor-background)",
    border: "1px solid var(--vscode-widget-border, var(--vscode-panel-border, #333))",
    padding: "8px 12px",
    borderRadius: "12px 12px 12px 2px",
    alignSelf: "flex-start",
    maxWidth: "95%",
    wordBreak: "break-word",
    whiteSpace: "pre-wrap",
  },
  system: {
    color: "var(--vscode-descriptionForeground)",
    fontSize: "0.85em",
    textAlign: "center" as const,
    padding: "4px 8px",
    fontStyle: "italic",
    alignSelf: "center",
  },
  toolUse: {
    background: "var(--vscode-textBlockQuote-background, rgba(255,255,255,0.05))",
    border: "1px solid var(--vscode-textBlockQuote-border, #444)",
    padding: "6px 10px",
    borderRadius: "6px",
    fontSize: "0.85em",
    fontFamily: "var(--vscode-editor-font-family)",
    alignSelf: "flex-start",
    maxWidth: "95%",
  },
  thinking: {
    color: "var(--vscode-descriptionForeground)",
    background: "transparent",
    borderLeft: "2px solid var(--vscode-textBlockQuote-border, #555)",
    padding: "4px 10px",
    fontSize: "0.85em",
    fontStyle: "italic",
    alignSelf: "flex-start",
    maxWidth: "95%",
    whiteSpace: "pre-wrap",
    opacity: 0.7,
  },
  result: {
    color: "var(--vscode-descriptionForeground)",
    fontSize: "0.8em",
    textAlign: "center" as const,
    padding: "4px 8px",
    alignSelf: "center",
  },
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const style = styles[message.type] ?? styles.system;

  const slackBadge = message.source === "slack" && (
    <span
      style={{
        fontSize: "0.7em",
        color: "var(--vscode-descriptionForeground)",
        marginLeft: "6px",
        opacity: 0.8,
      }}
    >
      (from Slack)
    </span>
  );

  const content = useMemo(() => {
    if (message.type === "toolUse") {
      return formatToolUse(message);
    }
    if (message.type === "result") {
      return formatResult(message);
    }
    return renderMarkdown(message.content);
  }, [message]);

  return (
    <div style={style}>
      {message.type === "user" && slackBadge}
      {message.isStreaming && (
        <span
          style={{
            display: "inline-block",
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: "var(--vscode-progressBar-background, #0078d4)",
            marginRight: "6px",
            animation: "pulse 1s infinite",
          }}
        />
      )}
      <span dangerouslySetInnerHTML={{ __html: content }} />
    </div>
  );
}

function formatToolUse(msg: ChatMessage): string {
  const inp = msg.toolInput as Record<string, unknown> | undefined;
  if (!inp) return `<code>${msg.toolName}</code>`;

  switch (msg.toolName) {
    case "Bash":
      return `<code style="color:var(--vscode-terminal-ansiCyan)">$ ${escapeHtml(truncate(String(inp.command ?? ""), 200))}</code>`;
    case "Read":
      return `<code>Read</code> <code>${escapeHtml(String(inp.file_path ?? ""))}</code>`;
    case "Write":
      return `<code>Write</code> <code>${escapeHtml(String(inp.file_path ?? ""))}</code>`;
    case "Edit":
      return `<code>Edit</code> <code>${escapeHtml(String(inp.file_path ?? ""))}</code>`;
    case "Glob":
      return `<code>Glob</code> <code>${escapeHtml(String(inp.pattern ?? ""))}</code>`;
    case "Grep":
      return `<code>Grep</code> <code>${escapeHtml(String(inp.pattern ?? ""))}</code>`;
    case "Task":
      return `<code>Task</code> ${escapeHtml(String(inp.description ?? ""))}`;
    default:
      return `<code>${escapeHtml(msg.toolName ?? "tool")}</code>`;
  }
}

function formatResult(msg: ChatMessage): string {
  const icon = msg.subtype === "success" ? "&#x2705;" : "&#x26A0;&#xFE0F;";
  const cost = msg.cost ? ` ($${msg.cost.toFixed(4)})` : "";
  const dur = msg.duration ? ` in ${(msg.duration / 1000).toFixed(1)}s` : "";
  return `${icon} <em>Complete${dur}${cost}</em>`;
}

function renderMarkdown(text: string): string {
  // Simple markdown rendering — code blocks, inline code, bold, italic
  let html = escapeHtml(text);

  // Code blocks
  html = html.replace(
    /```(\w*)\n([\s\S]*?)```/g,
    (_m, lang, code) =>
      `<pre style="background:var(--vscode-textCodeBlock-background,rgba(0,0,0,0.2));padding:8px;border-radius:4px;overflow-x:auto;font-size:0.9em"><code>${code}</code></pre>`
  );

  // Inline code
  html = html.replace(
    /`([^`]+)`/g,
    `<code style="background:var(--vscode-textCodeBlock-background,rgba(0,0,0,0.2));padding:1px 4px;border-radius:3px">$1</code>`
  );

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic
  html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");

  // Line breaks
  html = html.replace(/\n/g, "<br>");

  return html;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "...";
}

/**
 * Converts SDK message content to Slack mrkdwn format.
 */

/**
 * Convert markdown to Slack mrkdwn.
 * Slack uses different formatting than standard markdown.
 */
export function markdownToMrkdwn(text: string): string {
  let result = text;

  // Convert headers: ## Header → *Header*
  result = result.replace(/^#{1,6}\s+(.+)$/gm, "*$1*");

  // Convert bold: **text** → *text*
  result = result.replace(/\*\*(.+?)\*\*/g, "*$1*");

  // Convert italic: _text_ stays the same in Slack
  // Convert ~~strikethrough~~ → ~strikethrough~
  result = result.replace(/~~(.+?)~~/g, "~$1~");

  // Convert links: [text](url) → <url|text>
  result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "<$2|$1>");

  // Code blocks are already compatible (```)
  // Inline code is already compatible (`)

  return result;
}

/**
 * Format a tool use for Slack display.
 */
export function formatToolUse(
  toolName: string,
  toolInput: unknown
): string {
  const inp = toolInput as Record<string, unknown>;

  switch (toolName) {
    case "Bash":
      return `\`${toolName}\`:\n\`\`\`\n${truncate(String(inp.command ?? ""), 2000)}\n\`\`\``;

    case "Read":
      return `\`${toolName}\`: \`${inp.file_path}\``;

    case "Write":
      return `\`${toolName}\`: \`${inp.file_path}\` (${String(inp.content ?? "").length} chars)`;

    case "Edit": {
      const file = inp.file_path ?? "unknown";
      return `\`${toolName}\`: \`${file}\``;
    }

    case "Glob":
      return `\`${toolName}\`: \`${inp.pattern}\``;

    case "Grep":
      return `\`${toolName}\`: \`${inp.pattern}\``;

    case "WebSearch":
      return `\`${toolName}\`: "${inp.query}"`;

    case "Task":
      return `\`${toolName}\`: ${inp.description}`;

    case "EnterPlanMode":
    case "ExitPlanMode":
    case "TaskList":
    case "TaskGet":
      return `\`${toolName}\``;

    case "Skill":
      return `\`${toolName}\`: \`${inp.skill}\`${inp.args ? ` ${inp.args}` : ""}`;

    case "TaskCreate":
    case "TodoWrite":
      return `\`${toolName}\`: ${truncate(String(inp.subject ?? inp.content ?? ""), 200)}`;

    case "TaskUpdate":
      return `\`${toolName}\`: ${inp.status ?? ""}${inp.subject ? ` — ${inp.subject}` : ""}`;

    case "NotebookEdit":
      return `\`${toolName}\`: \`${inp.notebook_path}\``;

    default: {
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
        if (parts.length >= 4) break;
      }
      return `\`${toolName}\`: ${parts.length ? parts.join(", ") : "{}"}`;
    }
  }
}

/**
 * Format a result message for Slack.
 */
export function formatResult(
  subtype: string,
  cost: number,
  durationMs: number
): string {
  const costStr = cost ? ` ($${cost.toFixed(4)})` : "";
  const durationStr = durationMs
    ? ` in ${(durationMs / 1000).toFixed(1)}s`
    : "";
  const prefix = subtype === "success" ? "✅" : "⚠️";
  return `${prefix} _Complete${durationStr}${costStr}_`;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\n... (truncated)";
}

/**
 * Formats tool inputs for Discord markdown display.
 */

export function formatToolInput(toolName: string, input: unknown): string {
  if (!input || typeof input !== "object") return String(input);

  const inp = input as Record<string, unknown>;

  switch (toolName) {
    case "Bash":
      return `\`\`\`bash\n${truncate(String(inp.command ?? ""), 1800)}\n\`\`\``;
    case "Read":
      return `\`${inp.file_path}\``;
    case "Write":
      return `\`${inp.file_path}\` (${String(inp.content ?? "").length} chars)`;
    case "Edit":
      return `\`${inp.file_path}\``;
    case "Glob":
      return `\`${inp.pattern}\`${inp.path ? ` in \`${inp.path}\`` : ""}`;
    case "Grep":
      return `\`${inp.pattern}\`${inp.path ? ` in \`${inp.path}\`` : ""}`;
    case "WebSearch":
      return `"${inp.query}"`;
    case "WebFetch":
      return `\`${inp.url}\``;
    case "Task":
      return `${inp.description}: ${truncate(String(inp.prompt ?? ""), 200)}`;
    case "Agent":
      return truncate(String(inp.prompt ?? inp.description ?? ""), 200);
    case "EnterPlanMode":
    case "ExitPlanMode":
      return "";
    case "Skill":
      return `\`${inp.skill}\`${inp.args ? ` ${inp.args}` : ""}`;
    case "TaskCreate":
    case "TodoWrite":
      return truncate(String(inp.subject ?? inp.content ?? JSON.stringify(input)), 200);
    case "TaskUpdate":
      return `${inp.status ?? ""}${inp.subject ? ` — ${inp.subject}` : ""}`;
    case "TaskList":
    case "TaskGet":
      return "";
    case "NotebookEdit":
      return `\`${inp.notebook_path}\``;
    default:
      return formatDefaultInput(inp);
  }
}

/** Compact summary for unknown tools. */
function formatDefaultInput(inp: Record<string, unknown>): string {
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
  return parts.length ? parts.join("\n") : "{}";
}

export function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\n... (truncated)";
}

/**
 * Format a result message with cost and duration.
 */
export function formatResult(subtype: string, cost: number, durationMs: number): string {
  const costStr = cost ? ` ($${cost.toFixed(4)})` : "";
  const durationStr = durationMs ? ` in ${(durationMs / 1000).toFixed(1)}s` : "";
  return `*Session ${subtype}${durationStr}${costStr}*`;
}

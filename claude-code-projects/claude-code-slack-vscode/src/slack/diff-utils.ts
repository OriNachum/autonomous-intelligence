import * as path from "path";

const MAX_PREVIEW_BYTES = 8 * 1024; // 8KB

/**
 * Build a unified diff string for an Edit tool operation.
 */
export function buildEditDiff(input: {
  file_path: string;
  old_string: string;
  new_string: string;
}): string {
  const filename = path.basename(input.file_path);
  const oldLines = input.old_string.split("\n");
  const newLines = input.new_string.split("\n");

  const header = [
    `--- a/${filename}`,
    `+++ b/${filename}`,
    `@@ -1,${oldLines.length} +1,${newLines.length} @@`,
  ];

  const body = [
    ...oldLines.map((l) => `- ${l}`),
    ...newLines.map((l) => `+ ${l}`),
  ];

  return [...header, ...body].join("\n");
}

/**
 * Build a content preview for a Write tool operation, truncated to 8KB.
 */
export function buildWritePreview(input: {
  file_path: string;
  content: string;
}): string {
  const content = input.content ?? "";
  if (content.length <= MAX_PREVIEW_BYTES) return content;
  return content.slice(0, MAX_PREVIEW_BYTES) + "\n... (truncated)";
}

/**
 * Infer a Slack snippet_type from a file extension.
 * Returns undefined for unknown types (Slack auto-detects).
 */
export function inferSnippetType(
  filePath: string
): string | undefined {
  const ext = path.extname(filePath).toLowerCase();
  const map: Record<string, string> = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".html": "html",
    ".xml": "xml",
    ".json": "javascript",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".sql": "sql",
    ".diff": "diff",
    ".patch": "diff",
  };
  return map[ext];
}

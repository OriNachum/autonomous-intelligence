import React from "react";
import type { PendingPermission } from "../App";

interface PermissionPromptProps {
  permission: PendingPermission;
  onApprove: () => void;
  onDeny: () => void;
}

export function PermissionPrompt({
  permission,
  onApprove,
  onDeny,
}: PermissionPromptProps) {
  const inp = permission.toolInput as Record<string, unknown> | undefined;
  const summary = formatPermissionSummary(permission.toolName, inp);

  return (
    <div
      style={{
        background: "var(--vscode-inputValidation-warningBackground, rgba(255,200,0,0.1))",
        border: "1px solid var(--vscode-inputValidation-warningBorder, #cca700)",
        borderRadius: "8px",
        padding: "10px 12px",
        alignSelf: "flex-start",
        maxWidth: "95%",
      }}
    >
      <div
        style={{
          fontWeight: "bold",
          marginBottom: "6px",
          color: "var(--vscode-editorWarning-foreground, #cca700)",
          fontSize: "0.9em",
        }}
      >
        Permission: {permission.toolName}
      </div>

      <pre
        style={{
          background: "var(--vscode-textCodeBlock-background, rgba(0,0,0,0.2))",
          padding: "6px 8px",
          borderRadius: "4px",
          fontSize: "0.85em",
          fontFamily: "var(--vscode-editor-font-family)",
          overflow: "auto",
          maxHeight: "150px",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          marginBottom: "8px",
        }}
      >
        {summary}
      </pre>

      <div style={{ display: "flex", gap: "8px" }}>
        <button
          onClick={onApprove}
          style={{
            background: "var(--vscode-button-background)",
            color: "var(--vscode-button-foreground)",
            border: "none",
            borderRadius: "4px",
            padding: "5px 16px",
            cursor: "pointer",
            fontSize: "0.85em",
          }}
        >
          Allow
        </button>
        <button
          onClick={onDeny}
          style={{
            background: "transparent",
            color: "var(--vscode-foreground)",
            border: "1px solid var(--vscode-widget-border, #555)",
            borderRadius: "4px",
            padding: "5px 16px",
            cursor: "pointer",
            fontSize: "0.85em",
          }}
        >
          Deny
        </button>
      </div>
    </div>
  );
}

function formatPermissionSummary(
  toolName: string,
  input: Record<string, unknown> | undefined
): string {
  if (!input) return toolName;

  switch (toolName) {
    case "Bash":
      return String(input.command ?? "");
    case "Write":
      return `Write to ${input.file_path}\n(${String(input.content ?? "").length} chars)`;
    case "Edit":
      return `Edit ${input.file_path}`;
    case "Read":
      return `Read ${input.file_path}`;
    default:
      return JSON.stringify(input, null, 2).slice(0, 500);
  }
}

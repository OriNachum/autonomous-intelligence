import React from "react";

interface SessionControlsProps {
  onStop: () => void;
  onNewSession: () => void;
  isProcessing: boolean;
  slackConnected: boolean;
}

export function SessionControls({
  onStop,
  onNewSession,
  isProcessing,
  slackConnected,
}: SessionControlsProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        padding: "6px 12px",
        gap: "8px",
        borderBottom: "1px solid var(--vscode-widget-border, var(--vscode-panel-border, #333))",
        fontSize: "0.85em",
      }}
    >
      <span
        style={{
          fontWeight: "bold",
          color: "var(--vscode-foreground)",
          marginRight: "auto",
        }}
      >
        Claude + Slack
      </span>

      {/* Slack status badge */}
      <span
        title={slackConnected ? "Slack connected" : "Slack disconnected"}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          color: "var(--vscode-descriptionForeground)",
          fontSize: "0.9em",
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: "7px",
            height: "7px",
            borderRadius: "50%",
            background: slackConnected
              ? "var(--vscode-testing-iconPassed, #4caf50)"
              : "var(--vscode-testing-iconFailed, #f44336)",
          }}
        />
        Slack
      </span>

      {isProcessing && (
        <button
          onClick={onStop}
          title="Stop current query"
          style={{
            background: "var(--vscode-button-secondaryBackground, #333)",
            color: "var(--vscode-button-secondaryForeground, #ccc)",
            border: "none",
            borderRadius: "4px",
            padding: "3px 10px",
            cursor: "pointer",
            fontSize: "0.85em",
          }}
        >
          Stop
        </button>
      )}

      <button
        onClick={onNewSession}
        title="Start a new session"
        style={{
          background: "var(--vscode-button-secondaryBackground, #333)",
          color: "var(--vscode-button-secondaryForeground, #ccc)",
          border: "none",
          borderRadius: "4px",
          padding: "3px 10px",
          cursor: "pointer",
          fontSize: "0.85em",
        }}
      >
        New
      </button>
    </div>
  );
}

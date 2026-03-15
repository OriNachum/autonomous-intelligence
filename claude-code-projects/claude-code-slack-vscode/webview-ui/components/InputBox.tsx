import React, { useState, useRef, useCallback } from "react";

interface InputBoxProps {
  onSend: (text: string) => void;
  disabled: boolean;
}

export function InputBox({ onSend, disabled }: InputBoxProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [text, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setText(e.target.value);
      // Auto-resize
      const el = e.target;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    },
    []
  );

  return (
    <div
      style={{
        padding: "8px 12px",
        borderTop: "1px solid var(--vscode-widget-border, var(--vscode-panel-border, #333))",
        display: "flex",
        gap: "8px",
        alignItems: "flex-end",
      }}
    >
      <textarea
        ref={textareaRef}
        value={text}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Message Claude... (Enter to send, Shift+Enter for newline)"
        rows={1}
        style={{
          flex: 1,
          resize: "none",
          background: "var(--vscode-input-background)",
          color: "var(--vscode-input-foreground)",
          border: "1px solid var(--vscode-input-border, var(--vscode-widget-border, #444))",
          borderRadius: "6px",
          padding: "8px 10px",
          fontFamily: "var(--vscode-font-family)",
          fontSize: "var(--vscode-font-size)",
          outline: "none",
          lineHeight: "1.4",
          maxHeight: "200px",
          overflow: "auto",
        }}
      />
      <button
        onClick={handleSend}
        disabled={disabled || !text.trim()}
        style={{
          background: "var(--vscode-button-background)",
          color: "var(--vscode-button-foreground)",
          border: "none",
          borderRadius: "6px",
          padding: "8px 14px",
          cursor: disabled || !text.trim() ? "default" : "pointer",
          opacity: disabled || !text.trim() ? 0.5 : 1,
          fontSize: "var(--vscode-font-size)",
          fontFamily: "var(--vscode-font-family)",
          whiteSpace: "nowrap",
        }}
      >
        Send
      </button>
    </div>
  );
}

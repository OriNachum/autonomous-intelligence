import React, { useEffect, useState, useCallback, useRef } from "react";
import { ChatView } from "./components/ChatView";
import { InputBox } from "./components/InputBox";
import { SessionControls } from "./components/SessionControls";
import type {
  ExtensionToWebviewMessage,
  WebviewToExtensionMessage,
} from "../src/types";

// Acquire VS Code API
const vscode = (window as any).acquireVsCodeApi();

export interface ChatMessage {
  id: string;
  type: "user" | "assistant" | "system" | "toolUse" | "thinking" | "result";
  content: string;
  source?: "webview" | "slack";
  toolName?: string;
  toolInput?: unknown;
  isStreaming?: boolean;
  subtype?: string;
  cost?: number;
  duration?: number;
}

export interface PendingPermission {
  id: string;
  toolName: string;
  toolInput: unknown;
}

function postMessage(msg: WebviewToExtensionMessage) {
  vscode.postMessage(msg);
}

let msgCounter = 0;
function nextId(): string {
  return `msg_${++msgCounter}_${Date.now()}`;
}

export function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [permissions, setPermissions] = useState<PendingPermission[]>([]);
  const [slackConnected, setSlackConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const streamBufferRef = useRef<Map<string, string>>(new Map());

  const handleSend = useCallback((text: string) => {
    postMessage({ type: "sendMessage", text });
    setIsProcessing(true);
  }, []);

  const handleApprove = useCallback((id: string) => {
    postMessage({ type: "approvePermission", id });
    setPermissions((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const handleDeny = useCallback((id: string) => {
    postMessage({ type: "denyPermission", id });
    setPermissions((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const handleStop = useCallback(() => {
    postMessage({ type: "stopSession" });
    setIsProcessing(false);
  }, []);

  const handleNewSession = useCallback(() => {
    postMessage({ type: "newSession" });
    setMessages([]);
    setPermissions([]);
    setIsProcessing(false);
  }, []);

  // Listen for messages from the extension
  useEffect(() => {
    function handleMessage(event: MessageEvent<ExtensionToWebviewMessage>) {
      const msg = event.data;

      switch (msg.type) {
        case "user":
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              type: "user",
              content: msg.text,
              source: msg.source,
            },
          ]);
          break;

        case "assistant":
          for (const block of msg.content) {
            if (block.type === "text" && block.text) {
              setMessages((prev) => [
                ...prev,
                { id: nextId(), type: "assistant", content: block.text! },
              ]);
            }
          }
          setIsProcessing(false);
          break;

        case "system":
          setMessages((prev) => [
            ...prev,
            { id: nextId(), type: "system", content: msg.text },
          ]);
          break;

        case "toolUse":
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              type: "toolUse",
              content: `${msg.toolName}`,
              toolName: msg.toolName,
              toolInput: msg.toolInput,
            },
          ]);
          break;

        case "thinking":
          setMessages((prev) => {
            // Append to last thinking message if exists
            const last = prev[prev.length - 1];
            if (last?.type === "thinking") {
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + msg.text },
              ];
            }
            return [
              ...prev,
              { id: nextId(), type: "thinking", content: msg.text },
            ];
          });
          break;

        case "streamText": {
          const buf = streamBufferRef.current;
          const existing = buf.get(msg.messageId) ?? "";
          buf.set(msg.messageId, existing + msg.text);

          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.isStreaming && last.id === `stream_${msg.messageId}`) {
              return [
                ...prev.slice(0, -1),
                { ...last, content: buf.get(msg.messageId)! },
              ];
            }
            return [
              ...prev,
              {
                id: `stream_${msg.messageId}`,
                type: "assistant",
                content: buf.get(msg.messageId)!,
                isStreaming: true,
              },
            ];
          });
          break;
        }

        case "streamEnd":
          streamBufferRef.current.delete(msg.messageId);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === `stream_${msg.messageId}`
                ? { ...m, isStreaming: false }
                : m
            )
          );
          setIsProcessing(false);
          break;

        case "permissionRequest":
          setPermissions((prev) => [
            ...prev,
            {
              id: msg.id,
              toolName: msg.toolName,
              toolInput: msg.toolInput,
            },
          ]);
          break;

        case "permissionResolved":
          setPermissions((prev) => prev.filter((p) => p.id !== msg.id));
          break;

        case "slackStatus":
          setSlackConnected(msg.connected);
          break;

        case "result":
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              type: "result",
              content: `${msg.subtype === "success" ? "Complete" : msg.subtype}`,
              subtype: msg.subtype,
              cost: msg.cost,
              duration: msg.duration,
            },
          ]);
          setIsProcessing(false);
          break;

        case "clear":
          setMessages([]);
          setPermissions([]);
          setIsProcessing(false);
          break;
      }
    }

    window.addEventListener("message", handleMessage);
    // Tell extension we're ready
    postMessage({ type: "ready" });

    return () => window.removeEventListener("message", handleMessage);
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SessionControls
        onStop={handleStop}
        onNewSession={handleNewSession}
        isProcessing={isProcessing}
        slackConnected={slackConnected}
      />
      <ChatView
        messages={messages}
        permissions={permissions}
        onApprove={handleApprove}
        onDeny={handleDeny}
      />
      <InputBox onSend={handleSend} disabled={false} />
    </div>
  );
}

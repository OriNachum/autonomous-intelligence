import React, { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import { PermissionPrompt } from "./PermissionPrompt";
import type { ChatMessage, PendingPermission } from "../App";

interface ChatViewProps {
  messages: ChatMessage[];
  permissions: PendingPermission[];
  onApprove: (id: string) => void;
  onDeny: (id: string) => void;
}

export function ChatView({
  messages,
  permissions,
  onApprove,
  onDeny,
}: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, permissions]);

  return (
    <div
      style={{
        flex: 1,
        overflow: "auto",
        padding: "8px 12px",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      }}
    >
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {permissions.map((perm) => (
        <PermissionPrompt
          key={perm.id}
          permission={perm}
          onApprove={() => onApprove(perm.id)}
          onDeny={() => onDeny(perm.id)}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

import { Suspense, lazy } from "react";
import { ChatMessage, ChatMessageBubble, ChatToolCalls } from "@astryxdesign/core/Chat";
import { Banner } from "@astryxdesign/core/Banner";
import { CodeBlock } from "@astryxdesign/core/CodeBlock";
import { Markdown } from "@astryxdesign/core/Markdown";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";

import type { Step } from "../../lib/chatApi";
import type { ChatMessage as ChatMessageData } from "../../lib/useChat";
import { toCallItem } from "./toolCalls";
import TableWidget from "./widgets/TableWidget";

// The charting library is heavy; load it only when a chart actually appears.
const OhlcvChart = lazy(() => import("./widgets/OhlcvChart"));
const LineWidget = lazy(() => import("./widgets/LineWidget"));
const ProposalCard = lazy(() => import("./widgets/ProposalCard"));

type ToolStep = Extract<Step, { type: "tool" }>;

function preview(value: unknown, max = 1500): string {
  const text = (typeof value === "string" ? value : JSON.stringify(value, null, 2)) ?? "";
  return text.length > max ? `${text.slice(0, max)}\n… (${text.length - max} more characters)` : text;
}

function Widget({ step }: { step: ToolStep }) {
  const d = step.display;
  if (!d) return null;
  return (
    <Suspense fallback={<div className="chat-widget-loading">Loading…</div>}>
      {d.type === "ohlcv" ? (
        <OhlcvChart display={d} />
      ) : d.type === "line" ? (
        <LineWidget display={d} />
      ) : d.type === "proposal" ? (
        <ProposalCard display={d} />
      ) : (
        <TableWidget display={d} />
      )}
    </Suspense>
  );
}

export default function MessageView({ message }: { message: ChatMessageData }) {
  if (message.role === "user") {
    return (
      <ChatMessage sender="user">
        <ChatMessageBubble>{message.content}</ChatMessageBubble>
      </ChatMessage>
    );
  }

  const tools = message.steps.filter((s): s is ToolStep => s.type === "tool");
  const errors = message.steps.filter((s) => s.type === "error");
  const stopped = !message.pending && !message.content && !errors.length && !tools.length;
  const calls = tools.map((s, i) =>
    toCallItem(
      s,
      i,
      !!message.pending,
      // A call that is still running has no result to show yet.
      s.result === undefined ? undefined : (
        <CodeBlock
          code={preview(s.result)}
          language="json"
          size="sm"
          width="100%"
          maxHeight={220}
          container="section"
        />
      ),
    ),
  );

  return (
    <ChatMessage
      sender="assistant"
      metadata={
        !message.pending && message.model ? (
          <Text type="supporting" size="xsm">
            {message.model}
          </Text>
        ) : undefined
      }
    >
      {/* A ghost bubble keeps everything on the same text column as the answer. */}
      <ChatMessageBubble variant="ghost" width="100%">
        <div className="chat-assistant-body">
          {calls.length > 0 && <ChatToolCalls calls={calls} />}
          {tools.map((s, i) => (
            <Widget key={s.id ?? i} step={s} />
          ))}
          {message.content && <Markdown isStreaming={!!message.pending}>{message.content}</Markdown>}
          {message.pending && !message.content && (
            <div className="chat-thinking" role="status">
              <Spinner size="sm" />
              <Text type="supporting">{tools.length ? "Working…" : "Thinking…"}</Text>
            </div>
          )}
          {errors.map((e, i) => (
            <Banner key={i} status="error" title={e.type === "error" ? e.content : ""} />
          ))}
          {stopped && <Text type="supporting">Stopped.</Text>}
        </div>
      </ChatMessageBubble>
    </ChatMessage>
  );
}

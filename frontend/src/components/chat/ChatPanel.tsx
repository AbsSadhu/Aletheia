import { useCallback, useEffect, useState } from "react";
import { ChatComposer, ChatLayout, ChatMessageList } from "@astryxdesign/core/Chat";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Text } from "@astryxdesign/core/Text";
import { ArrowUpRight, BookOpen, History, LineChart, MessageSquarePlus, Trash2, TrendingUp, X } from "lucide-react";
import type { ComponentType, SVGProps } from "react";

import { deleteThread, getProviders, listThreads, resolveChoice } from "../../lib/chatApi";
import type { ModelChoice, ProvidersResponse, ThreadSummary } from "../../lib/chatApi";
import {
  loadChoice,
  saveChoice,
  setChatOpen,
  takePendingPrompt,
  toggleChat,
  useChatOpen,
  usePromptVersion,
} from "../../lib/chatPanelStore";
import { useChat } from "../../lib/useChat";
import ChatErrorBoundary from "./ChatErrorBoundary";
import MessageView from "./MessageView";
import ModelPicker from "./ModelPicker";
import "../../styles/chat.css";
import "../../styles/chatskin.css";

const SUGGESTIONS: { text: string; icon: ComponentType<SVGProps<SVGSVGElement>> }[] = [
  { text: "What is the latest price and 1-month trend for RELIANCE.NS?", icon: TrendingUp },
  { text: "Run technical analysis on TCS for 1 year", icon: LineChart },
  { text: "Summarise the fundamentals of INFY", icon: BookOpen },
];

/** Two rings and a core, turning in 3D: the assistant's mark. Pure CSS. */
function Orbit({ busy }: { busy: boolean }) {
  return (
    <span className={`orbit${busy ? " busy" : ""}`} aria-hidden="true">
      <i className="orbit-ring r1" />
      <i className="orbit-ring r2" />
      <i className="orbit-core" />
    </span>
  );
}

/**
 * Optional assistant drawer, available on every page. It talks to the agent through
 * /api/v1/chat/*; nothing else in the app depends on it. Built from Astryx's chat components
 * (message list, tool-call rows, streaming markdown, glass composer dock).
 */
function ChatPanelInner() {
  const open = useChatOpen();
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [choice, setChoice] = useState<ModelChoice | null>(loadChoice);
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [showThreads, setShowThreads] = useState(false);
  // What the user picked, unless that model is not actually available on this machine.
  const effectiveChoice = resolveChoice(choice, providers);
  const chat = useChat(effectiveChoice);

  const refreshProviders = useCallback(() => {
    getProviders()
      .then((p) => {
        setProviders(p);
        setProvidersError(null);
      })
      .catch((e: unknown) =>
        setProvidersError(e instanceof Error ? e.message : "Backend not reachable"),
      );
  }, []);

  useEffect(() => {
    if (open) refreshProviders();
  }, [open, refreshProviders]);

  // A question queued from the Cmd+K menu is sent as soon as the panel is open.
  const { send } = chat;
  const promptVersion = usePromptVersion();
  useEffect(() => {
    if (!open) return;
    const queued = takePendingPrompt();
    if (queued) void send(queued);
  }, [open, promptVersion, send]);

  // Ctrl/Cmd+J toggles the panel from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        toggleChat();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const choose = (c: ModelChoice) => {
    setChoice(c);
    saveChoice(c);
  };

  const toggleThreads = () => {
    const next = !showThreads;
    setShowThreads(next);
    if (next) {
      listThreads()
        .then(setThreads)
        .catch(() => setThreads([]));
    }
  };

  if (!open) return null;

  const empty = (
    <div className="chat-empty">
      <div className="chat-hero">
        <Orbit busy={false} />
        <h2 className="chat-hero-title">Ask the market.</h2>
        <p className="chat-hero-sub">
          Prices, charts, technicals, fundamentals and news, from your own data and the model you pick below.
        </p>
      </div>
      <div className="chat-suggestions">
        {SUGGESTIONS.map((sg, i) => (
          <button
            key={sg.text}
            type="button"
            className="chat-suggest"
            style={{ ["--n" as string]: i } as React.CSSProperties}
            onClick={() => void chat.send(sg.text)}
          >
            <sg.icon width={16} height={16} aria-hidden="true" />
            <span>{sg.text}</span>
            <ArrowUpRight width={15} height={15} className="chat-suggest-go" aria-hidden="true" />
          </button>
        ))}
      </div>
      <div className="chat-disclaimer">
        <Text type="supporting" size="xsm">
          Research assistance, not financial advice. The Oracle BUY/REDUCE signal failed its
          backtest and shouldn&apos;t be relied on.
        </Text>
      </div>
    </div>
  );

  return (
    <aside className="chat-panel" aria-label="Assistant">
      <header className="chat-header">
        <span className="chat-title">
          <Orbit busy={chat.streaming} />
          <Text type="label" weight="semibold">
            Assistant
          </Text>
        </span>
        <div className="chat-header-actions">
          <IconButton label="Past chats" tooltip="Past chats" icon={<History size={16} />} variant="ghost" size="sm" onClick={toggleThreads} />
          <IconButton
            label="New chat"
            tooltip="New chat"
            icon={<MessageSquarePlus size={16} />}
            variant="ghost"
            size="sm"
            onClick={() => {
              chat.reset();
              setShowThreads(false);
            }}
          />
          <IconButton label="Close assistant" tooltip="Close (Ctrl+J)" icon={<X size={16} />} variant="ghost" size="sm" onClick={() => setChatOpen(false)} />
        </div>
      </header>

      {showThreads ? (
        <div className="chat-threads">
          {threads === null && <Text type="supporting">Loading…</Text>}
          {threads?.length === 0 && <Text type="supporting">No saved chats yet.</Text>}
          {threads?.map((t) => (
            <div key={t.id} className={`chat-thread ${t.id === chat.threadId ? "active" : ""}`}>
              <button
                type="button"
                onClick={() => {
                  void chat.open(t.id).then(() => setShowThreads(false));
                }}
              >
                <span className="chat-thread-title">{t.title}</span>
                <span className="chat-muted">{t.model ?? ""}</span>
              </button>
              <IconButton
                label={`Delete chat ${t.title}`}
                icon={<Trash2 size={13} />}
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await deleteThread(t.id).catch(() => undefined);
                  if (t.id === chat.threadId) chat.reset();
                  setThreads((all) => all?.filter((x) => x.id !== t.id) ?? null);
                }}
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="chat-body">
          <ChatLayout
            density="compact"
            emptyState={empty}
            composer={
              <ChatComposer
                density="compact"
                placeholder="Ask anything…"
                onSubmit={(text) => void chat.send(text)}
                onStop={chat.stop}
                isStopShown={chat.streaming}
                footerActions={
                  <ModelPicker
                    providers={providers}
                    error={providersError}
                    choice={effectiveChoice}
                    onChoose={choose}
                    onRefresh={refreshProviders}
                    disabled={chat.streaming}
                  />
                }
              />
            }
          >
            {chat.messages.length > 0 ? (
              <ChatMessageList isStreaming={chat.streaming}>
                {chat.messages.map((m) => (
                  <MessageView key={m.id} message={m} />
                ))}
              </ChatMessageList>
            ) : null}
          </ChatLayout>
        </div>
      )}
    </aside>
  );
}

export default function ChatPanel() {
  return (
    <ChatErrorBoundary>
      <ChatPanelInner />
    </ChatErrorBoundary>
  );
}

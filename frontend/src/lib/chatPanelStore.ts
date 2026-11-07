import { useSyncExternalStore } from "react";

import type { ModelChoice } from "./chatApi";

// Open/closed state lives outside React so TopBar (rendered inside every page) can toggle the
// panel that App mounts once, without threading props through the router.
let open = false;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

export function setChatOpen(next: boolean): void {
  if (open === next) return;
  open = next;
  emit();
}

export const toggleChat = (): void => setChatOpen(!open);

// A prompt queued from elsewhere (the Cmd+K menu); the panel sends it once it is mounted.
let pendingPrompt: string | null = null;
let promptVersion = 0; // bumps on every queued prompt, so an already-open panel notices

export function askAssistant(prompt: string): void {
  pendingPrompt = prompt;
  promptVersion += 1;
  setChatOpen(true);
  emit();
}

/** Take the queued prompt, if any (returns it once). */
export function takePendingPrompt(): string | null {
  const p = pendingPrompt;
  pendingPrompt = null;
  return p;
}

export function usePromptVersion(): number {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => promptVersion,
  );
}

export function useChatOpen(): boolean {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => open,
  );
}

const CHOICE_KEY = "aletheia_chat_model";

export function loadChoice(): ModelChoice | null {
  try {
    const raw = localStorage.getItem(CHOICE_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw);
    return typeof v?.provider === "string" && typeof v?.model === "string" ? v : null;
  } catch {
    return null;
  }
}

export function saveChoice(choice: ModelChoice): void {
  try {
    localStorage.setItem(CHOICE_KEY, JSON.stringify(choice));
  } catch {
    /* storage unavailable: the choice just won't survive a reload */
  }
}

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CommandPalette } from "@astryxdesign/core/CommandPalette";
import { createStaticSource } from "@astryxdesign/core/Typeahead";
import type { SearchableItem, SearchSource } from "@astryxdesign/core/Typeahead";
import { Text } from "@astryxdesign/core/Text";

import { askAssistant, toggleChat } from "../lib/chatPanelStore";
import { resolveTheme, setTheme } from "../lib/theme";
import { NAV_ITEMS } from "./Sidebar";

type Group = "Pages" | "Actions" | "Assistant";
interface Command extends SearchableItem<{ group: Group; run: () => void; hint?: string }> {}

export function buildCommands(navigate: (to: string) => void): Command[] {
  const pages: Command[] = NAV_ITEMS.map((n) => ({
    id: `page:${n.to}`,
    label: n.label,
    auxiliaryData: { group: "Pages", run: () => navigate(n.to) },
  }));
  const actions: Command[] = [
    {
      id: "action:assistant",
      label: "Open the assistant",
      auxiliaryData: { group: "Actions", run: toggleChat, hint: "Ctrl J" },
    },
    {
      id: "action:theme",
      label: "Switch light / dark theme",
      auxiliaryData: {
        group: "Actions",
        run: () => setTheme(resolveTheme() === "dark" ? "light" : "dark"),
      },
    },
  ];
  return [...pages, ...actions];
}

/** Static commands, plus an "Ask the assistant" entry for whatever has been typed. */
export function buildSource(commands: Command[]): SearchSource<Command> {
  const base = createStaticSource(commands, {
    keywords: (c) => [c.auxiliaryData?.group ?? ""],
  });
  return {
    bootstrap: () => base.bootstrap?.() ?? commands,
    search: async (query: string) => {
      const found = await base.search(query);
      const q = query.trim();
      if (q.length < 3) return found;
      const ask: Command = {
        id: `ask:${q}`,
        label: `Ask the assistant: ${q}`,
        auxiliaryData: { group: "Assistant", run: () => askAssistant(q) },
      };
      return [...found, ask];
    },
  } as SearchSource<Command>;
}

/** Ctrl/Cmd+K launcher for pages, actions and quick questions to the assistant. */
export default function CommandMenu({ initiallyOpen = false }: { initiallyOpen?: boolean }) {
  const [open, setOpen] = useState(initiallyOpen);
  const navigate = useNavigate();
  const commands = useMemo(() => buildCommands(navigate), [navigate]);
  const source = useMemo(() => buildSource(commands), [commands]);
  const byId = useMemo(() => new Map(commands.map((c) => [c.id, c])), [commands]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = (id: string) => {
    const cmd = byId.get(id);
    if (cmd) {
      setOpen(false);
      cmd.auxiliaryData?.run();
    } else if (id.startsWith("ask:")) {
      setOpen(false);
      askAssistant(id.slice(4));
    }
  };

  return (
    <CommandPalette<Command>
      isOpen={open}
      onOpenChange={setOpen}
      searchSource={source}
      onValueChange={run}
      label="Command menu"
      emptySearchText="No matching pages or actions"
      renderItem={(item) => (
        <div className="cmdk-row">
          <Text type="body">{item.label}</Text>
          {item.auxiliaryData?.hint && (
            <Text type="supporting" size="xsm">
              {item.auxiliaryData.hint}
            </Text>
          )}
        </div>
      )}
    />
  );
}

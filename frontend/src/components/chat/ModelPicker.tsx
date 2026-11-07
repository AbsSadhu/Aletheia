import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Cpu, Cloud, Plus, Search, Trash2 } from "lucide-react";

import { deleteCustomModel } from "../../lib/chatApi";
import type { ModelChoice, ModelEntry, ProviderId, ProvidersResponse } from "../../lib/chatApi";
import AddModelForm, { formatBytes } from "./AddModelForm";

interface Props {
  providers: ProvidersResponse | null;
  error: string | null;
  choice: ModelChoice | null;
  onChoose: (choice: ModelChoice) => void;
  onRefresh: () => void;
  disabled?: boolean;
}

function sameChoice(a: ModelChoice | null, provider: string, m: ModelEntry): boolean {
  if (!a || a.provider !== provider) return false;
  return a.custom_model_id && m.custom_id
    ? a.custom_model_id === m.custom_id
    : a.model === m.model;
}

export default function ModelPicker({
  providers,
  error,
  choice,
  onChoose,
  onRefresh,
  disabled,
}: Props) {
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  // Effective selection: the saved choice, else the backend default.
  const active: ModelChoice | null =
    choice ?? (providers ? { provider: providers.default.provider, model: providers.default.model } : null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setAdding(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setAdding(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const activeEntry = useMemo(() => {
    if (!providers || !active) return null;
    const p = providers.providers.find((x) => x.id === active.provider);
    return p?.models.find((m) => sameChoice(active, p.id, m)) ?? null;
  }, [providers, active]);

  const q = query.trim().toLowerCase();
  const providerLabel = providers?.providers.find((p) => p.id === active?.provider)?.label;

  const choose = (provider: ProviderId, m: ModelEntry) => {
    onChoose({
      provider,
      model: m.model,
      custom_model_id: m.custom_id,
    });
    setOpen(false);
  };

  return (
    <div className="chat-model" ref={rootRef}>
      <button
        type="button"
        className="chat-model-trigger"
        onClick={() => {
          setOpen((o) => !o);
          setAdding(false);
          if (!open) onRefresh();
        }}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        title="Choose the model used for this chat"
      >
        <span
          className={`chat-dot ${
            error ? "bad" : providers?.providers.find((p) => p.id === active?.provider)?.available
              ? "ok"
              : "bad"
          }`}
        />
        <span className="chat-model-name">{active ? active.model : error ? "Offline" : "Loading…"}</span>
        {activeEntry?.parameter_size && (
          <span className="chat-chip">{activeEntry.parameter_size}</span>
        )}
        {providerLabel && <span className="chat-model-provider">{providerLabel}</span>}
        <ChevronDown size={14} />
      </button>

      {open && (
        <div className="chat-model-pop" role="dialog" aria-label="Choose model">
          {adding ? (
            <AddModelForm
              onCancel={() => setAdding(false)}
              onAdded={(c) => {
                setAdding(false);
                onChoose(c);
                onRefresh();
                setOpen(false);
              }}
            />
          ) : (
            <>
              <div className="chat-model-search">
                <Search size={14} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search models"
                  aria-label="Search models"
                  autoFocus
                />
              </div>
              <div className="chat-model-list" role="listbox">
                {error && <p className="chat-error">{error}</p>}
                {providers?.providers.map((p) => {
                  const models = p.models.filter(
                    (m) => !q || m.label.toLowerCase().includes(q) || m.model.toLowerCase().includes(q),
                  );
                  if (!models.length && q) return null; // while searching, hide groups with no match
                  return (
                    <div key={p.id} className="chat-model-group">
                      <div className="chat-model-group-title">
                        {p.id === "ollama" ? <Cpu size={12} /> : <Cloud size={12} />}
                        {p.label}
                        {!p.available && <span className="chat-chip warn">unavailable</span>}
                      </div>
                      {p.error && !p.available && <p className="chat-hint">{p.error}</p>}
                      {models.map((m) => {
                        const selected = sameChoice(active, p.id, m);
                        return (
                          <div
                            key={`${p.id}:${m.custom_id ?? m.model}`}
                            className={`chat-model-row ${selected ? "selected" : ""}`}
                          >
                            <button
                              type="button"
                              role="option"
                              aria-selected={selected}
                              className="chat-model-pick"
                              onClick={() => choose(p.id, m)}
                              disabled={!p.available}
                            >
                              <span className="chat-model-row-name">{m.label}</span>
                              {m.parameter_size && <span className="chat-chip">{m.parameter_size}</span>}
                              {!!m.size_bytes && (
                                <span className="chat-muted">{formatBytes(m.size_bytes)}</span>
                              )}
                              {!m.installed && <span className="chat-chip warn">not downloaded</span>}
                              {selected && <Check size={14} className="chat-check" />}
                            </button>
                            {m.custom_id && (
                              <button
                                type="button"
                                className="chat-icon-btn"
                                title="Remove from list (does not delete the model from disk)"
                                aria-label={`Remove ${m.label} from list`}
                                onClick={async () => {
                                  await deleteCustomModel(m.custom_id!).catch(() => undefined);
                                  onRefresh();
                                }}
                              >
                                <Trash2 size={13} />
                              </button>
                            )}
                          </div>
                        );
                      })}
                      {p.id === "ollama" && !models.length && p.available && (
                        <p className="chat-hint">No models on disk yet. Add one below.</p>
                      )}
                    </div>
                  );
                })}
              </div>
              <button type="button" className="chat-model-add" onClick={() => setAdding(true)}>
                <Plus size={14} /> Add model
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

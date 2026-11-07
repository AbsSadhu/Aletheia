import { useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { addCustomModel, pullModel } from "../../lib/chatApi";
import type { ModelChoice, ProviderId } from "../../lib/chatApi";

type Kind = "ollama" | "cloud" | "endpoint";

interface Props {
  /** called after a model was added; the parent refreshes the list and may select it */
  onAdded: (choice: ModelChoice) => void;
  onCancel: () => void;
}

export function formatBytes(n: number): string {
  if (!n) return "";
  const gb = n / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(n / 1e6)} MB`;
}

export default function AddModelForm({ onAdded, onCancel }: Props) {
  const [kind, setKind] = useState<Kind>("ollama");
  const [model, setModel] = useState("");
  const [cloudProvider, setCloudProvider] = useState<"openai" | "anthropic">("anthropic");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ status: string; pct: number | null } | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const provider: ProviderId =
    kind === "ollama" ? "ollama" : kind === "cloud" ? cloudProvider : "openai_compatible";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const name = model.trim();
    if (!name || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === "ollama") {
        const controller = new AbortController();
        abortRef.current = controller;
        await pullModel(
          name,
          (p) =>
            setProgress({
              status: p.status,
              pct: p.total ? Math.round(((p.completed ?? 0) / p.total) * 100) : null,
            }),
          controller.signal,
        );
      }
      const created = await addCustomModel({
        provider,
        model: name,
        base_url: kind === "endpoint" ? baseUrl.trim() : undefined,
        api_key: kind === "endpoint" && apiKey.trim() ? apiKey.trim() : undefined,
      });
      onAdded({ provider, model: name, custom_model_id: created.id });
    } catch (err) {
      if (!abortRef.current?.signal.aborted)
        setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      setProgress(null);
      abortRef.current = null;
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    onCancel();
  };

  return (
    <form className="chat-add" onSubmit={submit}>
      <div className="chat-add-tabs" role="tablist">
        {(
          [
            ["ollama", "Ollama"],
            ["cloud", "Cloud API"],
            ["endpoint", "Custom endpoint"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={kind === id}
            className={kind === id ? "active" : ""}
            disabled={busy}
            onClick={() => setKind(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {kind === "cloud" && (
        <label className="chat-field">
          Provider
          <select
            value={cloudProvider}
            onChange={(e) => setCloudProvider(e.target.value as "openai" | "anthropic")}
            disabled={busy}
          >
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai">OpenAI</option>
          </select>
        </label>
      )}

      {kind === "endpoint" && (
        <label className="chat-field">
          Base URL
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://localhost:1234/v1"
            disabled={busy}
            required
          />
        </label>
      )}

      <label className="chat-field">
        Model name
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder={
            kind === "ollama"
              ? "qwen2.5:7b"
              : kind === "cloud"
                ? "model id from the provider"
                : "model id on the server"
          }
          autoFocus
          disabled={busy}
          required
        />
      </label>

      {kind === "endpoint" && (
        <label className="chat-field">
          API key <span className="chat-muted">(optional)</span>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            autoComplete="off"
            disabled={busy}
          />
        </label>
      )}

      {kind === "ollama" && (
        <p className="chat-hint">
          Downloads the model into Ollama if it isn&apos;t on disk yet, then adds it to the list.
        </p>
      )}
      {kind === "cloud" && (
        <p className="chat-hint">
          Uses the API key saved in Settings for this provider; it&apos;s only the model name that
          is added here.
        </p>
      )}

      {progress && (
        <div className="chat-progress" role="status">
          <div className="chat-progress-bar">
            <span style={{ width: `${progress.pct ?? 8}%` }} />
          </div>
          <span>
            {progress.status}
            {progress.pct !== null ? ` · ${progress.pct}%` : ""}
          </span>
        </div>
      )}
      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}

      <div className="chat-add-actions">
        <button type="button" className="btn btn-ghost btn-sm" onClick={cancel}>
          {busy ? "Stop" : "Cancel"}
        </button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy || !model.trim()}>
          {busy ? (
            <Loader2 size={14} className="chat-spin" />
          ) : kind === "ollama" ? (
            <Download size={14} />
          ) : null}
          {kind === "ollama" ? "Download & add" : "Add model"}
        </button>
      </div>
    </form>
  );
}

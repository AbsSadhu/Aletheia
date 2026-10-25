import { useEffect, useState } from "react";
import { Save, Shield, Cpu, Key, Database, Radio, Check, AlertCircle, Eye, EyeOff, Lock } from "lucide-react";
import TopBar from "../components/TopBar";
import { fetchHealth, getSystemConfig, updateSystemConfig, getApiKey, setApiKey, zerodhaStatus, zerodhaLoginUrl, fyersStatus, fyersLoginUrl } from "../lib/api";
import type { HealthData } from "../lib/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [config, setConfig] = useState<Record<string, any>>({
    ollama_base_url: "",
    default_llm_model: "",
    default_llm_provider: "ollama",
    anthropic_api_key: "",
    openai_api_key: "",
    gemini_api_key: "",
    zerodha_api_key: "",
    zerodha_api_secret: "",
    angel_one_enabled: false,
    live_feed_provider: "angel_one",
    fyers_app_id: "",
    fyers_secret: "",
    angel_one_api_key: "",
    angel_one_client_code: "",
    angel_one_pin: "",
    angel_one_totp_secret: "",
    tradingview_session: "",
    yfinance_enabled: true,
    ccxt_enabled: true,
    sqlite_path: "",
    duckdb_path: "",
    log_dir: "",
    backup_dir: "",
  });

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Key visibility toggles
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  // Local API key used to authenticate to this backend, paired with its
  // ALETHEIA_API_KEYS env var (see SECURITY.md). Stored in localStorage
  // only — never sent to the server config endpoint.
  const [localApiKey, setLocalApiKey] = useState(() => getApiKey());
  const [apiKeySaved, setApiKeySaved] = useState(false);

  const [kite, setKite] = useState<{ configured: boolean; logged_in: boolean } | null>(null);
  const refreshKite = () => zerodhaStatus().then(setKite).catch(() => setKite(null));
  useEffect(() => {
    void refreshKite();
  }, []);

  // Opens Kite's login in a new tab; Kite redirects back to the backend callback, which
  // stores the daily token. Poll status afterwards so the badge updates without a reload.
  const handleKiteLogin = async () => {
    try {
      const { url } = await zerodhaLoginUrl();
      window.open(url, "_blank", "noopener");
      const timer = setInterval(() => void refreshKite(), 3000);
      setTimeout(() => clearInterval(timer), 120_000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Zerodha login");
    }
  };

  const [fy, setFy] = useState<{ configured: boolean; logged_in: boolean; redirect_uri: string } | null>(null);
  const refreshFy = () => fyersStatus().then(setFy).catch(() => setFy(null));
  useEffect(() => {
    void refreshFy();
  }, []);

  // Same pattern as Zerodha: login happens on Fyers' site, which redirects back to the backend.
  const handleFyersLogin = async () => {
    try {
      const { url } = await fyersLoginUrl();
      window.open(url, "_blank", "noopener");
      const timer = setInterval(() => void refreshFy(), 3000);
      setTimeout(() => clearInterval(timer), 120_000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start Fyers login");
    }
  };

  const handleSaveApiKey = () => {
    setApiKey(localApiKey.trim());
    setApiKeySaved(true);
    setTimeout(() => setApiKeySaved(false), 2000);
  };

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const healthData = await fetchHealth().catch(() => null);
        setHealth(healthData);

        const configData = await getSystemConfig();
        setConfig(configData);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load configuration");
      } finally {
        setLoading(false);
      }
    }
    void loadData();
  }, []);

  const handleToggleKey = (field: string) => {
    setShowKeys((prev) => ({ ...prev, [field]: !prev[field] }));
  };

  const handleChange = (field: string, value: any) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const savedConfig = await updateSystemConfig(config);
      setConfig(savedConfig);
      setSuccess("Configuration saved successfully! Server settings updated.");
      // Reload health in case database paths changed
      const healthData = await fetchHealth().catch(() => null);
      setHealth(healthData);
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update configuration");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <TopBar title="Settings" />
      <div className="page-shell">
        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "var(--space-12)" }}>
            <div className="spinner" />
          </div>
        ) : (
          <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)", maxWidth: "1000px", margin: "0 auto" }}>
            {error && (
              <div className="card" style={{ background: "var(--red-muted)", color: "var(--red)", borderColor: "var(--red)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <AlertCircle size={16} />
                  <span>{error}</span>
                </div>
              </div>
            )}

            {success && (
              <div className="card" style={{ background: "var(--green-muted)", color: "var(--green)", borderColor: "var(--green)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <Check size={16} />
                  <span>{success}</span>
                </div>
              </div>
            )}

            <div className="grid-2">
              {/* LLM settings */}
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                <div className="card-header" style={{ marginBottom: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <Cpu size={18} style={{ color: "var(--accent)" }} />
                    <div className="card-title">LLM Intelligence Router</div>
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                  <div>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      Frontier Provider
                    </label>
                    <select
                      className="form-control"
                      value={config.default_llm_provider}
                      onChange={(e) => handleChange("default_llm_provider", e.target.value)}
                      style={{ width: "100%" }}
                    >
                      <option value="ollama">Local (Ollama)</option>
                      <option value="openai">OpenAI (GPT)</option>
                      <option value="anthropic">Anthropic (Claude)</option>
                      <option value="gemini">Google (Gemini)</option>
                    </select>
                  </div>

                  {config.default_llm_provider === "ollama" ? (
                    <>
                      <div>
                        <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                          Ollama Host
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          value={config.ollama_base_url || ""}
                          onChange={(e) => handleChange("ollama_base_url", e.target.value)}
                          placeholder="http://localhost:11434"
                          style={{ width: "100%" }}
                        />
                      </div>
                      <div>
                        <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                          Ollama Model
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          value={config.default_llm_model || ""}
                          onChange={(e) => handleChange("default_llm_model", e.target.value)}
                          placeholder="mistral:7b"
                          style={{ width: "100%" }}
                        />
                      </div>
                    </>
                  ) : (
                    <>
                      {config.default_llm_provider === "openai" && (
                        <div>
                          <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                            OpenAI API Key
                          </label>
                          <div style={{ position: "relative" }}>
                            <input
                              type={showKeys.openai ? "text" : "password"}
                              className="form-control"
                              value={config.openai_api_key || ""}
                              onChange={(e) => handleChange("openai_api_key", e.target.value)}
                              placeholder={config.openai_api_key ? "********" : "Enter API Key"}
                              style={{ width: "100%", paddingRight: "40px" }}
                            />
                            <button
                              type="button"
                              onClick={() => handleToggleKey("openai")}
                              style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center" }}
                            >
                              {showKeys.openai ? <EyeOff size={16} /> : <Eye size={16} />}
                            </button>
                          </div>
                        </div>
                      )}

                      {config.default_llm_provider === "anthropic" && (
                        <div>
                          <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                            Anthropic API Key
                          </label>
                          <div style={{ position: "relative" }}>
                            <input
                              type={showKeys.anthropic ? "text" : "password"}
                              className="form-control"
                              value={config.anthropic_api_key || ""}
                              onChange={(e) => handleChange("anthropic_api_key", e.target.value)}
                              placeholder={config.anthropic_api_key ? "********" : "Enter API Key"}
                              style={{ width: "100%", paddingRight: "40px" }}
                            />
                            <button
                              type="button"
                              onClick={() => handleToggleKey("anthropic")}
                              style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center" }}
                            >
                              {showKeys.anthropic ? <EyeOff size={16} /> : <Eye size={16} />}
                            </button>
                          </div>
                        </div>
                      )}

                      {config.default_llm_provider === "gemini" && (
                        <div>
                          <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                            Gemini API Key
                          </label>
                          <div style={{ position: "relative" }}>
                            <input
                              type={showKeys.gemini ? "text" : "password"}
                              className="form-control"
                              value={config.gemini_api_key || ""}
                              onChange={(e) => handleChange("gemini_api_key", e.target.value)}
                              placeholder={config.gemini_api_key ? "********" : "Enter API Key"}
                              style={{ width: "100%", paddingRight: "40px" }}
                            />
                            <button
                              type="button"
                              onClick={() => handleToggleKey("gemini")}
                              style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center" }}
                            >
                              {showKeys.gemini ? <EyeOff size={16} /> : <Eye size={16} />}
                            </button>
                          </div>
                        </div>
                      )}

                      <div>
                        <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                          Default Model Name
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          value={config.default_llm_model || ""}
                          onChange={(e) => handleChange("default_llm_model", e.target.value)}
                          placeholder="e.g. gpt-4o-mini, claude-3-5-sonnet-latest"
                          style={{ width: "100%" }}
                        />
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Data feeds */}
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                <div className="card-header" style={{ marginBottom: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <Radio size={18} style={{ color: "var(--teal)" }} />
                    <div className="card-title">Market Data Feeds</div>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", justifyContent: "center", height: "100%" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>Yahoo Finance Feed</div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Supports NSE/BSE and crypto equities</div>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={config.yfinance_enabled}
                        onChange={(e) => handleChange("yfinance_enabled", e.target.checked)}
                      />
                      <span className="slider round"></span>
                    </label>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-4)" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>Per-second live feed from</div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Pick one broker; restart the backend after changing</div>
                    </div>
                    <select
                      className="form-control"
                      aria-label="Live feed provider"
                      value={config.live_feed_provider || "angel_one"}
                      onChange={(e) => handleChange("live_feed_provider", e.target.value)}
                    >
                      <option value="angel_one">Angel One</option>
                      <option value="fyers">Fyers</option>
                      <option value="bse_web">BSE website (free, unofficial, about 2s)</option>
                    </select>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-4)" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>Angel One Live Feed</div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Per-second NSE/BSE quotes (needs credentials below; restart the backend after changing)</div>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={!!config.angel_one_enabled}
                        onChange={(e) => handleChange("angel_one_enabled", e.target.checked)}
                      />
                      <span className="slider round"></span>
                    </label>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-4)" }}>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>CCXT Crypto Feed</div>
                      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>Supports international crypto exchanges (Binance, Coinbase)</div>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={config.ccxt_enabled}
                        onChange={(e) => handleChange("ccxt_enabled", e.target.checked)}
                      />
                      <span className="slider round"></span>
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <div className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="card-header" style={{ marginBottom: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <Lock size={18} style={{ color: "var(--amber)" }} />
                  <div className="card-title">Backend API Key</div>
                </div>
              </div>
              <p className="stat-label" style={{ margin: 0 }}>
                Only needed if this backend was started with <code>ALETHEIA_API_KEYS</code> set.
                Stored in this browser only — must match one of the configured keys.
              </p>
              <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
                <input
                  type="password"
                  className="form-control"
                  value={localApiKey}
                  onChange={(e) => setLocalApiKey(e.target.value)}
                  placeholder="Leave blank if the backend has no API keys configured"
                  style={{ flex: 1 }}
                />
                <button type="button" className="btn" onClick={handleSaveApiKey}>
                  {apiKeySaved ? <Check size={16} /> : <Save size={16} />}
                  {apiKeySaved ? "Saved" : "Save"}
                </button>
              </div>
            </div>

            <div className="grid-2">
              {/* Broker keys */}
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                <div className="card-header" style={{ marginBottom: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <Key size={18} style={{ color: "var(--amber)" }} />
                    <div className="card-title">Broker Integrations</div>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                  <div>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      Zerodha API Key (Kite Connect)
                    </label>
                    <input
                      type="text"
                      className="form-control"
                      value={config.zerodha_api_key || ""}
                      onChange={(e) => handleChange("zerodha_api_key", e.target.value)}
                      placeholder={config.zerodha_api_key ? "********" : "Enter API Key"}
                      style={{ width: "100%" }}
                    />
                  </div>

                  <div>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      Zerodha API Secret
                    </label>
                    <div style={{ position: "relative" }}>
                      <input
                        type={showKeys.zerodhaSecret ? "text" : "password"}
                        className="form-control"
                        value={config.zerodha_api_secret || ""}
                        onChange={(e) => handleChange("zerodha_api_secret", e.target.value)}
                        placeholder={config.zerodha_api_secret ? "********" : "Enter API Secret"}
                        style={{ width: "100%", paddingRight: "40px" }}
                      />
                      <button
                        type="button"
                        onClick={() => handleToggleKey("zerodhaSecret")}
                        style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center" }}
                      >
                        {showKeys.zerodhaSecret ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                    <button type="button" className="btn btn-ghost" onClick={handleKiteLogin} disabled={!kite?.configured}>
                      Connect Zerodha
                    </button>
                    <span style={{ fontSize: "var(--text-sm)", color: kite?.logged_in ? "var(--green)" : "var(--text-muted)" }}>
                      {kite?.logged_in ? "Connected (today)" : kite?.configured ? "Not logged in — tokens reset ~6 AM IST" : "Save API key and secret first"}
                    </span>
                  </div>

                  <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                    <div className="stat-label">Angel One SmartAPI (free live NSE/BSE quotes)</div>
                    {([
                      ["angel_one_api_key", "API key"],
                      ["angel_one_client_code", "Client code"],
                      ["angel_one_pin", "PIN"],
                      ["angel_one_totp_secret", "TOTP secret (base32)"],
                    ] as const).map(([field, label]) => (
                      <input
                        key={field}
                        type={field === "angel_one_client_code" ? "text" : "password"}
                        className="form-control"
                        aria-label={label}
                        value={config[field] || ""}
                        onChange={(e) => handleChange(field, e.target.value)}
                        placeholder={config[field] ? "********" : label}
                        style={{ width: "100%" }}
                      />
                    ))}
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                      Turn on "Angel One Live Feed" above, save, then restart the backend. Check the result on the Live Market page.
                    </span>
                  </div>

                  <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                    <div className="stat-label">Fyers (free per-second NSE stream)</div>
                    <input
                      type="text"
                      className="form-control"
                      aria-label="Fyers app ID"
                      value={config.fyers_app_id || ""}
                      onChange={(e) => handleChange("fyers_app_id", e.target.value)}
                      placeholder={config.fyers_app_id ? "********" : "App ID, like ABC123XYZ-100"}
                      style={{ width: "100%" }}
                    />
                    <input
                      type="password"
                      className="form-control"
                      aria-label="Fyers secret"
                      value={config.fyers_secret || ""}
                      onChange={(e) => handleChange("fyers_secret", e.target.value)}
                      placeholder={config.fyers_secret ? "********" : "App secret"}
                      style={{ width: "100%" }}
                    />
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                      <button type="button" className="btn btn-ghost" onClick={handleFyersLogin} disabled={!fy?.configured}>
                        Connect Fyers
                      </button>
                      <span style={{ fontSize: "var(--text-sm)", color: fy?.logged_in ? "var(--green)" : "var(--text-muted)" }}>
                        {fy?.logged_in ? "Logged in today" : fy?.configured ? "Not logged in. Tokens reset 06:30 IST daily" : "Save app ID and secret first"}
                      </span>
                    </div>
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                      Register this redirect URL in your Fyers app: <code>{fy?.redirect_uri ?? "http://127.0.0.1:8899/api/v1/brokers/fyers/callback"}</code>. One-time helper setup: <code>scripts/fyers_setup.py</code>. See docs/FYERS_SETUP.md.
                    </span>
                  </div>

                  <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "var(--space-4)" }}>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      TradingView Session Cookie
                    </label>
                    <div style={{ position: "relative" }}>
                      <input
                        type={showKeys.tradingview ? "text" : "password"}
                        className="form-control"
                        value={config.tradingview_session || ""}
                        onChange={(e) => handleChange("tradingview_session", e.target.value)}
                        placeholder={config.tradingview_session ? "********" : "session_id cookie value"}
                        style={{ width: "100%", paddingRight: "40px" }}
                      />
                      <button
                        type="button"
                        onClick={() => handleToggleKey("tradingview")}
                        style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center" }}
                      >
                        {showKeys.tradingview ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Local Paths */}
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                <div className="card-header" style={{ marginBottom: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                    <Database size={18} style={{ color: "var(--purple)" }} />
                    <div className="card-title">Paths & Storage</div>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
                  <div>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      SQLite Database Path
                    </label>
                    <input
                      type="text"
                      className="form-control"
                      value={config.sqlite_path || ""}
                      onChange={(e) => handleChange("sqlite_path", e.target.value)}
                      style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}
                    />
                  </div>

                  <div>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      DuckDB Market Cache Path
                    </label>
                    <input
                      type="text"
                      className="form-control"
                      value={config.duckdb_path || ""}
                      onChange={(e) => handleChange("duckdb_path", e.target.value)}
                      style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}
                    />
                  </div>

                  <div>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      Logs Directory
                    </label>
                    <input
                      type="text"
                      className="form-control"
                      value={config.log_dir || ""}
                      onChange={(e) => handleChange("log_dir", e.target.value)}
                      style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}
                    />
                  </div>

                  <div>
                    <label className="stat-label" style={{ display: "block", marginBottom: "var(--space-2)" }}>
                      Backup Directory
                    </label>
                    <input
                      type="text"
                      className="form-control"
                      value={config.backup_dir || ""}
                      onChange={(e) => handleChange("backup_dir", e.target.value)}
                      style={{ width: "100%", fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)" }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Health Info */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
              <div className="card-header" style={{ marginBottom: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                  <Shield size={18} style={{ color: "var(--green)" }} />
                  <div className="card-title">System Status</div>
                </div>
              </div>
              <div style={{ display: "flex", gap: "var(--space-8)", flexWrap: "wrap" }}>
                <div>
                  <span className="stat-label">Backend Health</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                    <span className={`status-dot${health ? "" : " offline"}`} />
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>
                      {health ? "Online / Operational" : "Offline"}
                    </span>
                  </div>
                </div>
                {health && (
                  <>
                    <div>
                      <span className="stat-label">Active Database</span>
                      <div style={{ fontSize: "var(--text-xs)", fontFamily: "var(--font-mono)", marginTop: 4, color: "var(--text-secondary)" }}>
                        {health.sqlite_path}
                      </div>
                    </div>
                    <div>
                      <span className="stat-label">Market Engine Cache</span>
                      <div style={{ fontSize: "var(--text-xs)", fontFamily: "var(--font-mono)", marginTop: 4, color: "var(--text-secondary)" }}>
                        {health.duckdb_path}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Save Button */}
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "var(--space-2)" }}>
              <button type="submit" className="btn btn-primary" disabled={saving} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", padding: "12px 24px" }}>
                {saving ? (
                  <>
                    <div className="spinner" style={{ width: 14, height: 14, borderLeftColor: "white" }} />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save size={16} />
                    Save Configuration
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </>
  );
}

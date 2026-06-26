import { useEffect, useState, useRef } from "react";
import {
  Briefcase,
  Plus,
  Trash2,
  Upload,
  Edit2,
  Save,
  X,
  Check,
  FileSpreadsheet,
  Info,
  DollarSign,
} from "lucide-react";

import TopBar from "../components/TopBar";
import {
  listPortfolios,
  savePortfolio,
  deletePortfolio,
} from "../lib/api";
import type { PortfolioData, Holding } from "../lib/types";

const SUGGESTED_SYMBOLS = [
  "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
  "BHARTIARTL", "SBI", "LICI", "ITC", "HINDUNILVR",
  "LT", "BAJFINANCE", "HCLTECH", "MARUTI", "SUNPHARMA",
  "ADANIENT", "KOTAKBANK", "TITAN", "AXISBANK", "ULTRACEMCO",
  "NTPC", "TATAMOTORS", "ONGC", "COALINDIA", "ADANIPORTS",
  "JIOFIN", "POWERGRID", "ASIANPAINT", "BPCL", "M&M"
];

export default function Portfolio() {
  const [portfolios, setPortfolios] = useState<PortfolioData[]>([]);
  const [selectedPortfolio, setSelectedPortfolio] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Portfolio form state
  const [newPortfolioName, setNewPortfolioName] = useState("");
  const [newPortfolioCurrency, setNewPortfolioCurrency] = useState("INR");
  const [isCreatingPortfolio, setIsCreatingPortfolio] = useState(false);

  // Holding form state
  const [symbolInput, setSymbolInput] = useState("");
  const [quantityInput, setQuantityInput] = useState("");
  const [priceInput, setPriceInput] = useState("");
  const [assetTypeInput, setAssetTypeInput] = useState<Holding["asset_type"]>("equity");
  const [exchangeInput, setExchangeInput] = useState("NSE");
  const [taxProfileInput, setTaxProfileInput] = useState<Holding["tax_profile"]>("equity");
  const [symbolSuggestions, setSymbolSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Edit inline holding state
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editQuantity, setEditQuantity] = useState("");
  const [editPrice, setEditPrice] = useState("");

  // CSV Import state
  const [csvContent, setCsvContent] = useState("");
  const [showCsvImport, setShowCsvImport] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const res = await listPortfolios();
      setPortfolios(res.portfolios);
      if (res.portfolios.length > 0) {
        // Retain selection if possible, otherwise select first
        const currentName = selectedPortfolio?.name;
        const matched = res.portfolios.find((p) => p.name === currentName);
        setSelectedPortfolio(matched || res.portfolios[0]);
      } else {
        setSelectedPortfolio(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load portfolios");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  // Show auto-dismiss messages
  const triggerSuccess = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  const triggerError = (msg: string) => {
    setError(msg);
    setTimeout(() => setError(null), 5000);
  };

  // Symbol Autocomplete
  const handleSymbolChange = (val: string) => {
    const uppercaseVal = val.toUpperCase();
    setSymbolInput(uppercaseVal);
    if (uppercaseVal.trim().length > 0) {
      const filtered = SUGGESTED_SYMBOLS.filter((sym) =>
        sym.startsWith(uppercaseVal)
      );
      setSymbolSuggestions(filtered);
      setShowSuggestions(true);
    } else {
      setSymbolSuggestions([]);
      setShowSuggestions(false);
    }
  };

  const selectSuggestion = (sym: string) => {
    setSymbolInput(sym);
    setShowSuggestions(false);
  };

  // Create named portfolio
  const handleCreatePortfolio = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPortfolioName.trim()) {
      triggerError("Portfolio name is required");
      return;
    }
    const name = newPortfolioName.trim();
    if (portfolios.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
      triggerError(`A portfolio named "${name}" already exists`);
      return;
    }

    const newPortfolio: PortfolioData = {
      name,
      base_currency: newPortfolioCurrency,
      holdings: [],
    };

    try {
      setLoading(true);
      await savePortfolio(newPortfolio);
      setNewPortfolioName("");
      setIsCreatingPortfolio(false);
      triggerSuccess(`Portfolio "${name}" created successfully!`);
      // Reload and select the newly created portfolio
      const res = await listPortfolios();
      setPortfolios(res.portfolios);
      const matched = res.portfolios.find((p) => p.name === name);
      setSelectedPortfolio(matched || newPortfolio);
    } catch (err) {
      triggerError(err instanceof Error ? err.message : "Failed to create portfolio");
    } finally {
      setLoading(false);
    }
  };

  // Delete portfolio
  const handleDeletePortfolio = async (name: string) => {
    if (!confirm(`Are you sure you want to delete "${name}"?`)) return;
    try {
      setLoading(true);
      await deletePortfolio(name);
      triggerSuccess(`Portfolio "${name}" deleted.`);
      await loadData();
    } catch (err) {
      triggerError(err instanceof Error ? err.message : "Failed to delete portfolio");
    } finally {
      setLoading(false);
    }
  };

  // Add Holding
  const handleAddHolding = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPortfolio) return;

    if (!symbolInput.trim()) {
      triggerError("Symbol is required");
      return;
    }
    const quantity = parseFloat(quantityInput);
    if (isNaN(quantity) || quantity <= 0) {
      triggerError("Quantity must be a positive number");
      return;
    }
    const price = parseFloat(priceInput);
    if (isNaN(price) || price < 0) {
      triggerError("Average Price must be a non-negative number");
      return;
    }

    const uppercaseSymbol = symbolInput.trim().toUpperCase();

    // Check if symbol already exists, if so update/add
    let updatedHoldings = [...selectedPortfolio.holdings];
    const existingIndex = updatedHoldings.findIndex(
      (h) => h.symbol.toUpperCase() === uppercaseSymbol
    );

    if (existingIndex > -1) {
      const existing = updatedHoldings[existingIndex];
      const newQty = existing.quantity + quantity;
      const newPrice =
        (existing.quantity * existing.average_price + quantity * price) / newQty;
      updatedHoldings[existingIndex] = {
        ...existing,
        quantity: parseFloat(newQty.toFixed(4)),
        average_price: parseFloat(newPrice.toFixed(2)),
      };
    } else {
      updatedHoldings.push({
        symbol: uppercaseSymbol,
        quantity,
        average_price: price,
        asset_type: assetTypeInput,
        exchange: exchangeInput.trim().toUpperCase(),
        tax_profile: taxProfileInput,
      });
    }

    const updatedPortfolio = {
      ...selectedPortfolio,
      holdings: updatedHoldings,
    };

    try {
      setLoading(true);
      await savePortfolio(updatedPortfolio);
      setSelectedPortfolio(updatedPortfolio);
      setSymbolInput("");
      setQuantityInput("");
      setPriceInput("");
      triggerSuccess(`Added ${uppercaseSymbol} holding.`);
      await loadData();
    } catch (err) {
      triggerError(err instanceof Error ? err.message : "Failed to add holding");
    } finally {
      setLoading(false);
    }
  };

  // Delete holding
  const handleDeleteHolding = async (index: number) => {
    if (!selectedPortfolio) return;
    const updatedHoldings = selectedPortfolio.holdings.filter((_, i) => i !== index);
    const updatedPortfolio = {
      ...selectedPortfolio,
      holdings: updatedHoldings,
    };

    try {
      setLoading(true);
      await savePortfolio(updatedPortfolio);
      setSelectedPortfolio(updatedPortfolio);
      triggerSuccess("Holding deleted.");
      await loadData();
    } catch (err) {
      triggerError(err instanceof Error ? err.message : "Failed to delete holding");
    } finally {
      setLoading(false);
    }
  };

  // Start Inline Editing holding
  const startEditHolding = (index: number, h: Holding) => {
    setEditingIndex(index);
    setEditQuantity(h.quantity.toString());
    setEditPrice(h.average_price.toString());
  };

  // Save Inline Edit holding
  const saveEditHolding = async (index: number) => {
    if (!selectedPortfolio) return;
    const qty = parseFloat(editQuantity);
    const price = parseFloat(editPrice);
    if (isNaN(qty) || qty <= 0) {
      triggerError("Quantity must be a positive number");
      return;
    }
    if (isNaN(price) || price < 0) {
      triggerError("Price must be a non-negative number");
      return;
    }

    const updatedHoldings = [...selectedPortfolio.holdings];
    updatedHoldings[index] = {
      ...updatedHoldings[index],
      quantity: qty,
      average_price: price,
    };

    const updatedPortfolio = {
      ...selectedPortfolio,
      holdings: updatedHoldings,
    };

    try {
      setLoading(true);
      await savePortfolio(updatedPortfolio);
      setSelectedPortfolio(updatedPortfolio);
      setEditingIndex(null);
      triggerSuccess("Holding updated.");
      await loadData();
    } catch (err) {
      triggerError(err instanceof Error ? err.message : "Failed to update holding");
    } finally {
      setLoading(false);
    }
  };

  // Simple CSV parser supporting: symbol,quantity,average_price[,asset_type,exchange,tax_profile]
  const handleCSVImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedPortfolio || !csvContent.trim()) return;

    const lines = csvContent.split("\n");
    const newHoldings: Holding[] = [];
    let errorLines: string[] = [];

    lines.forEach((line, i) => {
      const cleaned = line.trim();
      if (!cleaned || i === 0 && cleaned.toLowerCase().includes("symbol")) {
        // Skip empty lines or header row
        return;
      }

      const parts = cleaned.split(",").map((p) => p.trim());
      if (parts.length < 3) {
        errorLines.push(`Line ${i + 1}: too few columns (${cleaned})`);
        return;
      }

      const symbol = parts[0].toUpperCase();
      const qty = parseFloat(parts[1]);
      const price = parseFloat(parts[2]);

      if (!symbol) {
        errorLines.push(`Line ${i + 1}: Symbol is empty`);
        return;
      }
      if (isNaN(qty) || qty <= 0) {
        errorLines.push(`Line ${i + 1}: Invalid quantity "${parts[1]}"`);
        return;
      }
      if (isNaN(price) || price < 0) {
        errorLines.push(`Line ${i + 1}: Invalid price "${parts[2]}"`);
        return;
      }

      // Optional values with fallbacks
      const asset_type = (parts[3]?.toLowerCase() as Holding["asset_type"]) || "equity";
      const exchange = parts[4]?.toUpperCase() || "NSE";
      const tax_profile = (parts[5]?.toLowerCase() as Holding["tax_profile"]) || "equity";

      newHoldings.push({
        symbol,
        quantity: qty,
        average_price: price,
        asset_type,
        exchange,
        tax_profile,
      });
    });

    if (errorLines.length > 0) {
      triggerError(`CSV parsing errors:\n${errorLines.slice(0, 3).join("\n")}`);
      return;
    }

    if (newHoldings.length === 0) {
      triggerError("No valid holdings found in CSV.");
      return;
    }

    // Append to existing holdings, merging matching symbols
    const updatedHoldings = [...selectedPortfolio.holdings];
    newHoldings.forEach((newH) => {
      const matchIndex = updatedHoldings.findIndex(
        (h) => h.symbol.toUpperCase() === newH.symbol
      );
      if (matchIndex > -1) {
        const existing = updatedHoldings[matchIndex];
        const mergedQty = existing.quantity + newH.quantity;
        const mergedPrice =
          (existing.quantity * existing.average_price + newH.quantity * newH.average_price) /
          mergedQty;
        updatedHoldings[matchIndex] = {
          ...existing,
          quantity: parseFloat(mergedQty.toFixed(4)),
          average_price: parseFloat(mergedPrice.toFixed(2)),
        };
      } else {
        updatedHoldings.push(newH);
      }
    });

    const updatedPortfolio = {
      ...selectedPortfolio,
      holdings: updatedHoldings,
    };

    try {
      setLoading(true);
      await savePortfolio(updatedPortfolio);
      setSelectedPortfolio(updatedPortfolio);
      setCsvContent("");
      setShowCsvImport(false);
      triggerSuccess(`Successfully imported ${newHoldings.length} holdings from CSV.`);
      await loadData();
    } catch (err) {
      triggerError(err instanceof Error ? err.message : "Failed to import CSV");
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target?.result as string;
      if (text) {
        setCsvContent(text);
        setShowCsvImport(true);
      }
    };
    reader.readAsText(file);
  };

  return (
    <>
      <TopBar title="Portfolio Manager" onRefresh={() => void loadData()} loading={loading} />
      <div className="page-shell">
        {error && (
          <div
            style={{
              padding: "var(--space-3) var(--space-4)",
              background: "var(--red-muted)",
              borderRadius: "var(--radius-md)",
              color: "var(--red)",
              fontSize: "var(--text-sm)",
              marginBottom: "var(--space-4)",
              whiteSpace: "pre-line",
            }}
          >
            ❌ {error}
          </div>
        )}
        {successMsg && (
          <div
            style={{
              padding: "var(--space-3) var(--space-4)",
              background: "var(--green-muted)",
              borderRadius: "var(--radius-md)",
              color: "var(--green)",
              fontSize: "var(--text-sm)",
              marginBottom: "var(--space-4)",
              display: "flex",
              alignItems: "center",
              gap: "var(--space-2)",
            }}
          >
            <Check size={16} /> {successMsg}
          </div>
        )}

        <div className="grid-layout-portfolio" style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "var(--space-5)" }}>
          {/* Left Panel: Portfolio List */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div className="card" style={{ padding: "var(--space-4)" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "var(--space-4)",
                }}
              >
                <div className="card-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Briefcase size={16} className="text-secondary" /> Portfolios
                </div>
                {!isCreatingPortfolio && (
                  <button
                    className="btn btn-ghost"
                    onClick={() => setIsCreatingPortfolio(true)}
                    style={{ padding: 4 }}
                    title="New Portfolio"
                  >
                    <Plus size={16} />
                  </button>
                )}
              </div>

              {isCreatingPortfolio && (
                <form
                  onSubmit={handleCreatePortfolio}
                  style={{
                    background: "var(--bg-elevated)",
                    padding: "var(--space-3)",
                    borderRadius: "var(--radius-md)",
                    marginBottom: "var(--space-4)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "var(--space-2)",
                    border: "1px solid var(--border-medium)",
                  }}
                >
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-secondary)" }}>
                    CREATE PORTFOLIO
                  </div>
                  <input
                    type="text"
                    placeholder="Portfolio Name"
                    value={newPortfolioName}
                    onChange={(e) => setNewPortfolioName(e.target.value)}
                    style={{
                      padding: "6px 10px",
                      background: "var(--bg-input)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      color: "var(--text-primary)",
                      fontSize: "var(--text-sm)",
                    }}
                    autoFocus
                  />
                  <select
                    value={newPortfolioCurrency}
                    onChange={(e) => setNewPortfolioCurrency(e.target.value)}
                    style={{
                      padding: "6px 10px",
                      background: "var(--bg-input)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      color: "var(--text-primary)",
                      fontSize: "var(--text-sm)",
                    }}
                  >
                    <option value="INR">INR (₹)</option>
                    <option value="USD">USD ($)</option>
                  </select>
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-2)", marginTop: 4 }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => setIsCreatingPortfolio(false)}
                    >
                      <X size={12} />
                    </button>
                    <button type="submit" className="btn btn-primary btn-sm">
                      Create
                    </button>
                  </div>
                </form>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
                {portfolios.length > 0 ? (
                  portfolios.map((p) => (
                    <div
                      key={p.name}
                      onClick={() => setSelectedPortfolio(p)}
                      style={{
                        padding: "var(--space-3)",
                        borderRadius: "var(--radius-md)",
                        background: selectedPortfolio?.name === p.name ? "var(--accent-muted)" : "var(--bg-elevated)",
                        border: selectedPortfolio?.name === p.name ? "1px solid var(--accent)" : "1px solid transparent",
                        cursor: "pointer",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        transition: "all var(--transition-fast)",
                      }}
                      className="portfolio-list-item"
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: "var(--text-sm)", color: selectedPortfolio?.name === p.name ? "var(--accent)" : "var(--text-primary)" }}>
                          {p.name}
                        </div>
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>
                          {p.holdings.length} holding{p.holdings.length !== 1 ? "s" : ""} · {p.base_currency}
                        </div>
                      </div>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDeletePortfolio(p.name);
                        }}
                        style={{ color: "var(--red)", opacity: 0.6, padding: 4 }}
                        title="Delete Portfolio"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))
                ) : (
                  <div style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "var(--text-xs)", padding: "var(--space-4)" }}>
                    No portfolios. Click + to create one.
                  </div>
                )}
              </div>
            </div>

            {/* Quick CSV helper info card */}
            <div className="card" style={{ padding: "var(--space-4)", fontSize: "var(--text-xs)", color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 600, color: "var(--text-primary)" }}>
                <Info size={14} className="text-secondary" /> CSV Format Guide
              </div>
              <p>Upload or paste CSV with these columns:</p>
              <code style={{ display: "block", background: "var(--bg-input)", padding: 6, borderRadius: "var(--radius-sm)", fontFamily: "var(--font-mono)", fontSize: 10 }}>
                symbol, quantity, average_price, [asset_type], [exchange], [tax_profile]
              </code>
              <p>Example:</p>
              <code style={{ display: "block", background: "var(--bg-input)", padding: 6, borderRadius: "var(--radius-sm)", fontFamily: "var(--font-mono)", fontSize: 10 }}>
                RELIANCE, 5, 2500.50, equity, NSE, equity<br />
                TCS, 3, 3700.00, equity, NSE, equity
              </code>
            </div>
          </div>

          {/* Right Panel: Selected Portfolio Editor */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            {selectedPortfolio ? (
              <>
                {/* Header Info */}
                <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "var(--space-4)" }}>
                  <div>
                    <h2 style={{ fontSize: "var(--text-lg)", fontWeight: 700 }}>{selectedPortfolio.name}</h2>
                    <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: 4 }}>
                      Base Currency: <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-secondary)" }}>{selectedPortfolio.base_currency}</span>
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: "var(--space-2)" }}>
                    <button
                      className="btn btn-secondary"
                      onClick={() => setShowCsvImport(!showCsvImport)}
                    >
                      <FileSpreadsheet size={16} />
                      CSV Paste Import
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Upload size={16} />
                      Upload CSV File
                    </button>
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileUpload}
                      accept=".csv"
                      style={{ display: "none" }}
                    />
                  </div>
                </div>

                {/* CSV Import Panel */}
                {showCsvImport && (
                  <div className="card" style={{ background: "var(--bg-elevated)", border: "1px solid var(--accent)" }}>
                    <div className="card-header" style={{ marginBottom: "var(--space-3)" }}>
                      <div className="card-title">Paste CSV Data</div>
                      <button className="btn btn-ghost" onClick={() => setShowCsvImport(false)}>
                        <X size={16} />
                      </button>
                    </div>
                    <form onSubmit={handleCSVImport} style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                      <textarea
                        placeholder="symbol,quantity,average_price&#10;RELIANCE,10,2500&#10;INFY,5,1500"
                        value={csvContent}
                        onChange={(e) => setCsvContent(e.target.value)}
                        style={{
                          height: 120,
                          padding: "var(--space-3)",
                          background: "var(--bg-input)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-md)",
                          color: "var(--text-primary)",
                          fontFamily: "var(--font-mono)",
                          fontSize: "var(--text-sm)",
                          resize: "vertical",
                        }}
                      />
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-2)" }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setCsvContent("")}
                        >
                          Clear
                        </button>
                        <button type="submit" className="btn btn-primary btn-sm">
                          Parse & Import
                        </button>
                      </div>
                    </form>
                  </div>
                )}

                {/* Holdings Table */}
                <div className="card">
                  <div className="card-title" style={{ marginBottom: "var(--space-4)" }}>
                    Holdings ({selectedPortfolio.holdings.length})
                  </div>
                  {selectedPortfolio.holdings.length > 0 ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Symbol</th>
                            <th>Exchange</th>
                            <th>Asset Type</th>
                            <th style={{ textAlign: "right" }}>Quantity</th>
                            <th style={{ textAlign: "right" }}>Avg Price</th>
                            <th style={{ textAlign: "right" }}>Total Cost</th>
                            <th style={{ textAlign: "right" }}>Tax Profile</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedPortfolio.holdings.map((h, index) => {
                            const isEditing = editingIndex === index;
                            return (
                              <tr key={index}>
                                <td style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-primary)" }}>
                                  {h.symbol}
                                </td>
                                <td>
                                  <span className="badge badge-pending" style={{ fontSize: 10 }}>{h.exchange}</span>
                                </td>
                                <td>
                                  <span style={{ fontSize: "var(--text-xs)", textTransform: "capitalize" }}>
                                    {h.asset_type}
                                  </span>
                                </td>
                                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                                  {isEditing ? (
                                    <input
                                      type="number"
                                      value={editQuantity}
                                      onChange={(e) => setEditQuantity(e.target.value)}
                                      style={{
                                        width: 80,
                                        textAlign: "right",
                                        background: "var(--bg-input)",
                                        border: "1px solid var(--accent)",
                                        borderRadius: "var(--radius-sm)",
                                        color: "white",
                                        padding: "2px 4px",
                                      }}
                                    />
                                  ) : (
                                    h.quantity
                                  )}
                                </td>
                                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                                  {isEditing ? (
                                    <input
                                      type="number"
                                      value={editPrice}
                                      onChange={(e) => setEditPrice(e.target.value)}
                                      style={{
                                        width: 90,
                                        textAlign: "right",
                                        background: "var(--bg-input)",
                                        border: "1px solid var(--accent)",
                                        borderRadius: "var(--radius-sm)",
                                        color: "white",
                                        padding: "2px 4px",
                                      }}
                                    />
                                  ) : (
                                    `${selectedPortfolio.base_currency === "INR" ? "₹" : "$"}${h.average_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`
                                  )}
                                </td>
                                <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-primary)" }}>
                                  {selectedPortfolio.base_currency === "INR" ? "₹" : "$"}{(h.quantity * h.average_price).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                                </td>
                                <td style={{ textAlign: "right" }}>
                                  <span className="badge badge-completed" style={{ fontSize: 10, background: "rgba(20, 184, 166, 0.08)", color: "var(--teal)" }}>
                                    {h.tax_profile}
                                  </span>
                                </td>
                                <td>
                                  <div style={{ display: "flex", justifyContent: "flex-end", gap: 4 }}>
                                    {isEditing ? (
                                      <>
                                        <button
                                          className="btn btn-ghost"
                                          onClick={() => void saveEditHolding(index)}
                                          style={{ color: "var(--green)", padding: 4 }}
                                          title="Save"
                                        >
                                          <Check size={14} />
                                        </button>
                                        <button
                                          className="btn btn-ghost"
                                          onClick={() => setEditingIndex(null)}
                                          style={{ color: "var(--text-muted)", padding: 4 }}
                                          title="Cancel"
                                        >
                                          <X size={14} />
                                        </button>
                                      </>
                                    ) : (
                                      <>
                                        <button
                                          className="btn btn-ghost"
                                          onClick={() => startEditHolding(index, h)}
                                          style={{ color: "var(--accent)", padding: 4 }}
                                          title="Edit Quantity/Price"
                                        >
                                          <Edit2 size={14} />
                                        </button>
                                        <button
                                          className="btn btn-ghost"
                                          onClick={() => void handleDeleteHolding(index)}
                                          style={{ color: "var(--red)", padding: 4 }}
                                          title="Remove Holding"
                                        >
                                          <Trash2 size={14} />
                                        </button>
                                      </>
                                    )}
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="empty-state" style={{ padding: "var(--space-6)" }}>
                      <div className="empty-state-title" style={{ fontSize: "var(--text-base)" }}>No holdings yet</div>
                      <div className="empty-state-text">
                        Use the form below or upload a CSV to add symbols to this portfolio.
                      </div>
                    </div>
                  )}
                </div>

                {/* Add Holding Form */}
                <div className="card">
                  <div className="card-title" style={{ marginBottom: "var(--space-4)" }}>Add Holding</div>
                  <form onSubmit={handleAddHolding} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "var(--space-3)", alignItems: "flex-end" }}>
                    {/* Symbol Input with Autocomplete */}
                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)", position: "relative" }}>
                      <label style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-secondary)" }}>SYMBOL</label>
                      <input
                        type="text"
                        placeholder="e.g. RELIANCE"
                        value={symbolInput}
                        onChange={(e) => handleSymbolChange(e.target.value)}
                        onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                        onFocus={() => symbolInput.length > 0 && setShowSuggestions(true)}
                        style={{
                          padding: "8px 12px",
                          background: "var(--bg-input)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-md)",
                          color: "var(--text-primary)",
                          fontSize: "var(--text-sm)",
                          fontFamily: "var(--font-mono)",
                        }}
                      />
                      {showSuggestions && symbolSuggestions.length > 0 && (
                        <div
                          style={{
                            position: "absolute",
                            top: "100%",
                            left: 0,
                            right: 0,
                            background: "var(--bg-elevated)",
                            border: "1px solid var(--border-medium)",
                            borderRadius: "var(--radius-md)",
                            zIndex: 10,
                            maxHeight: 150,
                            overflowY: "auto",
                            boxShadow: "var(--shadow-lg)",
                            marginTop: 4,
                          }}
                        >
                          {symbolSuggestions.map((sym) => (
                            <div
                              key={sym}
                              onMouseDown={() => selectSuggestion(sym)}
                              style={{
                                padding: "6px 12px",
                                cursor: "pointer",
                                fontSize: "var(--text-xs)",
                                fontFamily: "var(--font-mono)",
                                transition: "background var(--transition-fast)",
                              }}
                              className="autocomplete-item"
                            >
                              {sym}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
                      <label style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-secondary)" }}>QUANTITY</label>
                      <input
                        type="number"
                        step="any"
                        placeholder="Quantity"
                        value={quantityInput}
                        onChange={(e) => setQuantityInput(e.target.value)}
                        style={{
                          padding: "8px 12px",
                          background: "var(--bg-input)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-md)",
                          color: "var(--text-primary)",
                          fontSize: "var(--text-sm)",
                          fontFamily: "var(--font-mono)",
                        }}
                      />
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
                      <label style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-secondary)" }}>AVG BUY PRICE</label>
                      <input
                        type="number"
                        step="any"
                        placeholder="Price"
                        value={priceInput}
                        onChange={(e) => setPriceInput(e.target.value)}
                        style={{
                          padding: "8px 12px",
                          background: "var(--bg-input)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-md)",
                          color: "var(--text-primary)",
                          fontSize: "var(--text-sm)",
                          fontFamily: "var(--font-mono)",
                        }}
                      />
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
                      <label style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-secondary)" }}>ASSET TYPE</label>
                      <select
                        value={assetTypeInput}
                        onChange={(e) => setAssetTypeInput(e.target.value as Holding["asset_type"])}
                        style={{
                          padding: "8px 12px",
                          background: "var(--bg-input)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-md)",
                          color: "var(--text-primary)",
                          fontSize: "var(--text-sm)",
                        }}
                      >
                        <option value="equity">Equity</option>
                        <option value="etf">ETF</option>
                        <option value="future">Future</option>
                        <option value="crypto">Crypto</option>
                        <option value="cash">Cash</option>
                      </select>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
                      <label style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: "var(--text-secondary)" }}>TAX PROFILE</label>
                      <select
                        value={taxProfileInput}
                        onChange={(e) => setTaxProfileInput(e.target.value as Holding["tax_profile"])}
                        style={{
                          padding: "8px 12px",
                          background: "var(--bg-input)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-md)",
                          color: "var(--text-primary)",
                          fontSize: "var(--text-sm)",
                        }}
                      >
                        <option value="equity">Equity (India)</option>
                        <option value="fno">F&O (India)</option>
                        <option value="crypto">Crypto (India)</option>
                        <option value="mutual_fund">Mutual Fund (India)</option>
                      </select>
                    </div>

                    <button type="submit" className="btn btn-primary" style={{ height: 38, display: "flex", justifyContent: "center" }}>
                      <Plus size={14} /> Add
                    </button>
                  </form>
                </div>
              </>
            ) : (
              <div className="card">
                <div className="empty-state">
                  <div className="empty-state-icon">
                    <Briefcase size={48} strokeWidth={1} />
                  </div>
                  <div className="empty-state-title">Select a Portfolio</div>
                  <div className="empty-state-text">
                    Choose an existing portfolio from the list, or click the plus icon to create a new portfolio.
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

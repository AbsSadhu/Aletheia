import type { AgentEvent, HealthData, PortfolioData, RunResult, RunSummary } from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8899";

export async function fetchHealth(): Promise<HealthData> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`);
  if (!response.ok) {
    throw new Error("Failed to fetch health");
  }
  return response.json();
}

export async function listRuns(): Promise<{ runs: RunSummary[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/runs`);
  if (!response.ok) {
    throw new Error("Failed to list runs");
  }
  return response.json();
}

export async function getRun(runId: string): Promise<RunResult> {
  const response = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}`);
  if (!response.ok) {
    throw new Error("Run not found");
  }
  return response.json();
}

export async function createRun(
  prompt: string,
  portfolio?: PortfolioData,
  background: boolean = false
): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/api/v1/runs?background=${background}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, portfolio }),
  });
  if (!response.ok) {
    throw new Error("Failed to create analysis run");
  }
  return response.json();
}

export async function createDemoRun(): Promise<RunResult> {
  return createRun("Analyze an India-first starter portfolio", {
    name: "Starter",
    base_currency: "INR",
    holdings: [
      {
        symbol: "RELIANCE",
        quantity: 5,
        average_price: 2500,
        asset_type: "equity",
        exchange: "NSE",
        tax_profile: "equity",
      },
      {
        symbol: "TCS",
        quantity: 3,
        average_price: 3700,
        asset_type: "equity",
        exchange: "NSE",
        tax_profile: "equity",
      },
      {
        symbol: "INFY",
        quantity: 8,
        average_price: 1480,
        asset_type: "equity",
        exchange: "NSE",
        tax_profile: "equity",
      },
      {
        symbol: "HDFCBANK",
        quantity: 4,
        average_price: 1650,
        asset_type: "equity",
        exchange: "NSE",
        tax_profile: "equity",
      },
    ],
  });
}

export async function listPortfolios(): Promise<{ portfolios: PortfolioData[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/portfolios`);
  if (!response.ok) {
    throw new Error("Failed to list portfolios");
  }
  return response.json();
}

export async function getPortfolio(name: string): Promise<PortfolioData> {
  const response = await fetch(`${API_BASE_URL}/api/v1/portfolios/${encodeURIComponent(name)}`);
  if (!response.ok) {
    throw new Error("Failed to fetch portfolio");
  }
  return response.json();
}

export async function savePortfolio(portfolio: PortfolioData): Promise<PortfolioData> {
  const response = await fetch(`${API_BASE_URL}/api/v1/portfolios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(portfolio),
  });
  if (!response.ok) {
    throw new Error("Failed to save portfolio");
  }
  return response.json();
}

export async function deletePortfolio(name: string): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/api/v1/portfolios/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  return response.ok;
}

export async function getRunEvents(runId: string): Promise<{ events: AgentEvent[] }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/runs/${runId}/events`);
  if (!response.ok) {
    throw new Error("Failed to fetch run events");
  }
  return response.json();
}

export function getWebSocketUrl(runId: string): string {
  const wsBase = API_BASE_URL.replace(/^http/, "ws");
  return `${wsBase}/api/v1/ws/runs/${runId}`;
}

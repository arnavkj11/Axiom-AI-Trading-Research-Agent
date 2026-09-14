/**
 * Typed wrappers over the Axiom API.
 *
 * Calls go straight to the backend from the browser, which works because
 * the API allows this origin via CORSMiddleware (see backend
 * app/main.py + the `frontend_origin` setting). If the frontend is ever
 * served from somewhere else, both NEXT_PUBLIC_API_BASE_URL here and
 * `frontend_origin` there have to change together.
 */

import type {
  CompanyFilingsResponse,
  CompanyFinancialsResponse,
  CompanyLookupResponse,
  Company,
  ResearchRunCreated,
  ResearchRunDetail,
  ResearchRunListResponse,
  ResearchRunStatusResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // fetch only rejects on network-level failure, which in practice
    // means the API isn't running — worth saying so plainly rather than
    // surfacing "Failed to fetch".
    throw new ApiError(`Could not reach the Axiom API at ${API_BASE_URL}`, 0);
  }

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status);
  }
  return (await response.json()) as T;
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // Non-JSON error body; fall through to the generic message.
  }
  return `Request failed (${response.status})`;
}

export function searchCompanies(query: string): Promise<{ results: Company[] }> {
  return request("/companies/search", {
    method: "POST",
    body: JSON.stringify({ query }),
  });
}

export function getCompany(ticker: string): Promise<Company> {
  return request(`/companies/${ticker}`);
}

/**
 * Searches SEC's registrant list — companies that *could* be added, as
 * opposed to searchCompanies() which only covers the local database.
 */
export function lookupRegistrants(query: string): Promise<CompanyLookupResponse> {
  return request(`/companies/lookup?q=${encodeURIComponent(query)}`);
}

/**
 * Adds a company by ticker, resolving its identity from SEC's registrant
 * list. Idempotent — adding one that already exists returns it.
 */
export function addCompany(ticker: string): Promise<Company> {
  return request("/companies", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
}

export function getFinancials(ticker: string): Promise<CompanyFinancialsResponse> {
  return request(`/companies/${ticker}/financials`);
}

/**
 * Refetches financials from Alpha Vantage, bypassing the cache. Spends 4
 * of the free tier's 25 daily requests, so it's only ever user-initiated.
 */
export function refreshFinancials(
  ticker: string,
): Promise<CompanyFinancialsResponse> {
  return request(`/companies/${ticker}/financials/refresh`, { method: "POST" });
}

export function getFilings(ticker: string): Promise<CompanyFilingsResponse> {
  return request(`/companies/${ticker}/filings`);
}

export function syncFilings(ticker: string): Promise<CompanyFilingsResponse> {
  return request(`/companies/${ticker}/filings/sync`, { method: "POST" });
}

export function startResearch(ticker: string): Promise<ResearchRunCreated> {
  return request(`/companies/${ticker}/research`, { method: "POST" });
}

/**
 * Past runs, newest first. Summaries only — open one by id for its report.
 */
export function listResearchRuns(
  ticker?: string,
  limit = 20,
): Promise<ResearchRunListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (ticker) params.set("ticker", ticker);
  return request(`/research?${params.toString()}`);
}

export function getResearchRun(runId: number): Promise<ResearchRunDetail> {
  return request(`/research/${runId}`);
}

export function getResearchRunStatus(
  runId: number,
): Promise<ResearchRunStatusResponse> {
  return request(`/research/${runId}/status`);
}

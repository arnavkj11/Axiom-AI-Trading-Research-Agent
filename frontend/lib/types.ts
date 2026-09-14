/**
 * TypeScript mirrors of the backend's Pydantic schemas.
 *
 * Hand-written rather than generated from the OpenAPI schema — V1 doesn't
 * warrant the codegen toolchain. The tradeoff: these drift silently if the
 * backend schemas change. The types that matter most to keep in sync are
 * Evidence (a discriminated union keyed on `evidence_type`, matching
 * app/agents/schemas.py) and ResearchRunStatus.
 */

export type Stance = "BULLISH" | "BEARISH" | "NEUTRAL";

export type ResearchRunStatus =
  | "PENDING"
  | "RUNNING"
  | "FUNDAMENTAL_RUNNING"
  | "FILING_RUNNING"
  | "VALUATION_RUNNING"
  | "BULL_RUNNING"
  | "BEAR_RUNNING"
  | "JUDGE_RUNNING"
  | "COMPLETE"
  | "FAILED";

export const TERMINAL_STATUSES: ResearchRunStatus[] = ["COMPLETE", "FAILED"];

export function isTerminal(status: ResearchRunStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}

/* --- Evidence ------------------------------------------------------- */
// Every variant is self-describing: each carries enough to render what it
// points at without a second API call.

export interface FinancialMetricEvidence {
  evidence_type: "financial_metric";
  metric_id: number;
  metric_name: string;
  period_end: string;
  value: number;
}

export interface FilingChunkEvidence {
  evidence_type: "filing_chunk";
  chunk_id: number;
  filing_id: number;
  accession_number: string;
  section: string | null;
  quote: string;
}

export interface ValuationOutputEvidence {
  evidence_type: "valuation_output";
  research_run_id: number;
  function_name: string;
  output_field: string;
  value: number;
  assumptions: Record<string, number>;
}

export type Evidence =
  | FinancialMetricEvidence
  | FilingChunkEvidence
  | ValuationOutputEvidence;

export interface Finding {
  claim: string;
  importance: number;
  evidence: Evidence[];
}

/* --- Agent outputs -------------------------------------------------- */

export interface FundamentalAnalysis {
  stance: Stance;
  confidence: number;
  findings: Finding[];
  risks: Finding[];
}

export interface FilingAnalysis {
  stance: Stance;
  confidence: number;
  findings: Finding[];
  risks: Finding[];
}

export interface ScenarioValuation {
  scenario: "bear" | "base" | "bull";
  fair_value_per_share: number;
  assumptions: Record<string, number>;
  /** (fair_value − price) / price. Null when no quote was available. */
  upside_pct: number | null;
}

export interface ValuationOutput {
  method: string;
  scenarios: ScenarioValuation[];
  current_price: number | null;
  evidence: Evidence[];
  commentary: string;
}

export interface DebateCase {
  thesis: string;
  confidence: number;
  findings: Finding[];
  rebuttal: string | null;
  rebuttal_findings: Finding[];
}

export type BullCase = DebateCase;
export type BearCase = DebateCase;

export interface JudgeVerdict {
  stance: Stance;
  conviction: number;
  synthesis: string;
  bull_summary: string;
  bear_summary: string;
  rebuttal_summary: string;
  key_findings: Finding[];
  risks: Finding[];
  catalysts: Finding[];
}

/* --- Company / financials / filings --------------------------------- */

export interface Company {
  id: number;
  ticker: string;
  name: string;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  cik: string | null;
  /** When cached data was last pulled from its source; null if never. */
  financials_refreshed_at: string | null;
  filings_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

/** An SEC registrant that could be added to the database. */
export interface CompanyCandidate {
  ticker: string;
  name: string;
  cik: string;
  in_database: boolean;
}

export interface CompanyLookupResponse {
  candidates: CompanyCandidate[];
}

export interface FinancialMetricRecord {
  id: number;
  metric_name: string;
  period_end: string;
  period_type: string;
  value: number;
}

export interface FinancialPeriod {
  period_end: string;
  period_type: string;
  revenue: number | null;
  revenue_growth: number | null;
  gross_margin: number | null;
  operating_margin: number | null;
  net_income: number | null;
  eps: number | null;
  free_cash_flow: number | null;
  capex: number | null;
  debt: number | null;
  cash: number | null;
  share_count: number | null;
}

export interface CompanyFinancialsResponse {
  ticker: string;
  periods: FinancialPeriod[];
}

export interface FilingRead {
  id: number;
  accession_number: string;
  form_type: string;
  filing_date: string;
  period_end: string | null;
  published_at: string;
  source_url: string;
  status: string;
}

export interface CompanyFilingsResponse {
  ticker: string;
  filings: FilingRead[];
}

/* --- Research runs -------------------------------------------------- */

export type RecommendationAction = "BUY" | "SELL" | "HOLD" | "NOT_RATED";

/**
 * Computed in Python from the verdict and the valuation — never by a
 * model. Carries the thresholds it was computed under so it stays
 * interpretable if the product decision behind them changes.
 */
export interface Recommendation {
  action: RecommendationAction;
  stance: Stance | null;
  conviction: number | null;
  base_upside_pct: number | null;
  bear_upside_pct: number | null;
  thresholds: Record<string, number>;
  rationale: string;
}

export interface ResearchState {
  research_run_id: number;
  company_id: number;
  ticker: string;
  research_date: string;
  status: ResearchRunStatus;
  error: string | null;
  current_price: number | null;
  price_as_of: string | null;
  company: Company | null;
  financial_metrics: FinancialMetricRecord[];
  fundamental_analysis: FundamentalAnalysis | null;
  filing_analysis: FilingAnalysis | null;
  valuation_output: ValuationOutput | null;
  bull_case: BullCase | null;
  bear_case: BearCase | null;
  judge_verdict: JudgeVerdict | null;
  recommendation: Recommendation | null;
}

/** One row of run history — no report attached; fetch it by id. */
export interface ResearchRunSummary {
  research_run_id: number;
  ticker: string;
  status: ResearchRunStatus;
  research_date: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  stance: Stance | null;
  conviction: number | null;
  has_report: boolean;
}

export interface ResearchRunListResponse {
  runs: ResearchRunSummary[];
}

export interface ResearchRunCreated {
  research_run_id: number;
  ticker: string;
  status: ResearchRunStatus;
}

export interface ResearchRunStatusResponse {
  research_run_id: number;
  status: ResearchRunStatus;
}

export interface ResearchRunDetail {
  research_run_id: number;
  ticker: string;
  status: ResearchRunStatus;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  price_at_run: number | null;
  price_as_of: string | null;
  financials_as_of: string | null;
  filings_as_of: string | null;
  report: ResearchState | null;
}

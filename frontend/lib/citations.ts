/**
 * Builds the numbered source list behind the report's citations.
 *
 * The same piece of evidence is typically cited by several agents (the
 * Bull case argues from a metric the Fundamental Analyst surfaced, the
 * Judge cites it again in its verdict), so evidence is deduped by
 * identity and numbered once. Every `[n]` marker anywhere in the report
 * refers to the same entry in the sources panel.
 */

import type { Evidence, Finding, ResearchState } from "./types";

/** Stable identity for a piece of evidence, for deduping across agents. */
export function evidenceKey(evidence: Evidence): string {
  switch (evidence.evidence_type) {
    case "financial_metric":
      return `metric:${evidence.metric_id}`;
    case "filing_chunk":
      return `chunk:${evidence.chunk_id}`;
    case "valuation_output":
      return `valuation:${evidence.function_name}:${evidence.output_field}`;
  }
}

export interface Source {
  number: number;
  key: string;
  evidence: Evidence;
}

export interface CitationIndex {
  sources: Source[];
  /** Citation number for a piece of evidence, or undefined if uncited. */
  numberFor: (evidence: Evidence) => number | undefined;
}

function findingsOf(report: ResearchState): Finding[] {
  const groups: (Finding[] | undefined)[] = [
    report.fundamental_analysis?.findings,
    report.fundamental_analysis?.risks,
    report.filing_analysis?.findings,
    report.filing_analysis?.risks,
    report.bull_case?.findings,
    report.bull_case?.rebuttal_findings,
    report.bear_case?.findings,
    report.bear_case?.rebuttal_findings,
    report.judge_verdict?.key_findings,
    report.judge_verdict?.risks,
    report.judge_verdict?.catalysts,
  ];
  return groups.flatMap((group) => group ?? []);
}

export function buildCitationIndex(report: ResearchState): CitationIndex {
  const byKey = new Map<string, Source>();

  const add = (evidence: Evidence) => {
    const key = evidenceKey(evidence);
    if (!byKey.has(key)) {
      byKey.set(key, { number: byKey.size + 1, key, evidence });
    }
  };

  // Ordered so the numbering roughly follows the pipeline: findings from
  // the analysts first, then the valuation outputs they were argued from.
  findingsOf(report).forEach((finding) => finding.evidence.forEach(add));
  report.valuation_output?.evidence.forEach(add);

  const sources = [...byKey.values()];
  return {
    sources,
    numberFor: (evidence) => byKey.get(evidenceKey(evidence))?.number,
  };
}

/** DOM id for a source entry, so citation markers can link to it. */
export function sourceElementId(key: string): string {
  return `source-${key.replace(/[^a-zA-Z0-9]/g, "-")}`;
}

/**
 * Split into two parts so the sources list can column-align them —
 * identifiers under identifiers, qualifiers under qualifiers — which
 * scans far better than one run-on string per row.
 */
export function evidenceLabel(evidence: Evidence): {
  primary: string;
  secondary: string;
} {
  switch (evidence.evidence_type) {
    case "financial_metric":
      return {
        primary: evidence.metric_name.replace(/_/g, " "),
        secondary: evidence.period_end,
      };
    case "filing_chunk":
      return {
        primary: evidence.accession_number,
        secondary: evidence.section ?? "",
      };
    case "valuation_output":
      return {
        primary: `${evidence.function_name}()`,
        secondary: evidence.output_field,
      };
  }
}

export function evidenceKindLabel(evidence: Evidence): string {
  switch (evidence.evidence_type) {
    case "financial_metric":
      return "Financial metric";
    case "filing_chunk":
      return "SEC filing";
    case "valuation_output":
      return "Valuation output";
  }
}

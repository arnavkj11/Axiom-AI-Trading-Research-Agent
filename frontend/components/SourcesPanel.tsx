"use client";

import type { CitationIndex } from "@/lib/citations";
import { evidenceLabel, sourceElementId } from "@/lib/citations";
import type { Evidence } from "@/lib/types";

/** Colour-codes the kind of evidence, so the mix is readable at a glance. */
const KIND = {
  financial_metric: { label: "Metric", color: "var(--color-signal)" },
  filing_chunk: { label: "Filing", color: "var(--color-muted)" },
  valuation_output: { label: "Calculation", color: "var(--color-bull)" },
} as const;

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-xs text-faint">{term}</dt>
      <dd className="text-sm text-fg">{children}</dd>
    </>
  );
}

/**
 * What a citation actually points at. Every Evidence variant arrives
 * self-describing from the API, so nothing here needs a second request.
 */
function EvidenceDetail({ evidence }: { evidence: Evidence }) {
  switch (evidence.evidence_type) {
    case "financial_metric":
      return (
        <dl className="grid grid-cols-[7rem_1fr] gap-x-4 gap-y-2">
          <Row term="Metric">
            <span className="capitalize">
              {evidence.metric_name.replace(/_/g, " ")}
            </span>
          </Row>
          <Row term="Value">
            <span className="tnum">{evidence.value.toLocaleString()}</span>
          </Row>
          <Row term="Period end">
            <span className="tnum">{evidence.period_end}</span>
          </Row>
          <Row term="Row id">
            <span className="tnum text-faint">{evidence.metric_id}</span>
          </Row>
        </dl>
      );

    case "filing_chunk":
      return (
        <div>
          <blockquote className="border-l border-line pl-4 font-display text-[15px] italic leading-[1.7] text-fg">
            {evidence.quote}
          </blockquote>
          <dl className="mt-4 grid grid-cols-[7rem_1fr] gap-x-4 gap-y-2">
            <Row term="Filing">
              <span className="tnum">{evidence.accession_number}</span>
            </Row>
            {evidence.section && <Row term="Section">{evidence.section}</Row>}
            <Row term="Chunk id">
              <span className="tnum text-faint">{evidence.chunk_id}</span>
            </Row>
          </dl>
        </div>
      );

    case "valuation_output":
      return (
        <dl className="grid grid-cols-[7rem_1fr] gap-x-4 gap-y-2">
          <Row term="Function">
            <span className="tnum">{evidence.function_name}()</span>
          </Row>
          <Row term="Output">
            <span className="tnum">{evidence.output_field}</span>
          </Row>
          <Row term="Value">
            <span className="tnum">{evidence.value.toLocaleString()}</span>
          </Row>
          {Object.keys(evidence.assumptions).length > 0 && (
            <Row term="Inputs">
              <span className="tnum text-[13px] text-muted">
                {Object.entries(evidence.assumptions)
                  .map(([name, value]) => `${name} ${value}`)
                  .join("   ")}
              </span>
            </Row>
          )}
        </dl>
      );
  }
}

export default function SourcesPanel({ citations }: { citations: CitationIndex }) {
  if (citations.sources.length === 0) {
    return <p className="text-sm text-faint">This run cited no evidence.</p>;
  }

  return (
    <ol className="border-t border-line-soft">
      {citations.sources.map((source) => {
        const kind = KIND[source.evidence.evidence_type];
        return (
          <li
            key={source.key}
            id={sourceElementId(source.key)}
            className="border-b border-line-soft target:bg-surface"
          >
            <details className="group">
              <summary className="flex cursor-pointer list-none items-center gap-4 py-3.5 transition-colors hover:bg-surface">
                <span className="tnum w-6 shrink-0 text-[13px] text-signal">
                  {source.number}
                </span>
                <span
                  className="w-20 shrink-0 text-xs"
                  style={{ color: kind.color }}
                >
                  {kind.label}
                </span>
                <span className="tnum min-w-0 flex-1 truncate text-[13px] text-fg">
                  {evidenceLabel(source.evidence).primary}
                </span>
                <span className="tnum hidden w-56 shrink-0 truncate text-[13px] text-faint sm:block">
                  {evidenceLabel(source.evidence).secondary}
                </span>
                <span className="shrink-0 pr-1 text-xs text-faint group-open:hidden">
                  Open
                </span>
                <span className="hidden shrink-0 pr-1 text-xs text-faint group-open:block">
                  Close
                </span>
              </summary>
              <div className="pb-5 pl-10 pr-4">
                <EvidenceDetail evidence={source.evidence} />
              </div>
            </details>
          </li>
        );
      })}
    </ol>
  );
}

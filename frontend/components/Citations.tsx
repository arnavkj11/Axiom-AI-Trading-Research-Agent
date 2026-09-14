"use client";

import type { CitationIndex } from "@/lib/citations";
import { sourceElementId, evidenceKey } from "@/lib/citations";
import type { Evidence, Finding } from "@/lib/types";

/** Numbered markers linking a claim to the evidence it rests on. */
function CitationMarkers({
  evidence,
  citations,
}: {
  evidence: Evidence[];
  citations: CitationIndex;
}) {
  if (evidence.length === 0) return null;
  return (
    <span className="ml-1.5 inline-flex gap-1 align-baseline">
      {evidence.map((item) => {
        const number = citations.numberFor(item);
        if (number === undefined) return null;
        return (
          <a
            key={evidenceKey(item)}
            href={`#${sourceElementId(evidenceKey(item))}`}
            className="tnum text-[11px] leading-none text-signal/70 underline decoration-signal/30 underline-offset-[3px] transition-colors hover:text-signal hover:decoration-signal"
            title="Jump to the evidence"
          >
            {number}
          </a>
        );
      })}
    </span>
  );
}

export function FindingList({
  findings,
  citations,
  emptyLabel = "None recorded.",
}: {
  findings: Finding[];
  citations: CitationIndex;
  emptyLabel?: string;
}) {
  if (findings.length === 0) {
    return <p className="text-sm text-faint">{emptyLabel}</p>;
  }
  return (
    <ul className="space-y-2.5">
      {findings.map((finding, index) => (
        <li key={index} className="flex gap-2.5 text-sm leading-relaxed">
          {/* Weight bar: how much the agent leaned on this claim, shown
              rather than spelled out as a number beside every line. */}
          <span
            className="mt-[7px] h-1 w-4 shrink-0 rounded-full bg-line"
            title={`Importance ${finding.importance.toFixed(2)}`}
          >
            <span
              className="block h-full rounded-full bg-muted"
              style={{ width: `${Math.round(finding.importance * 100)}%` }}
            />
          </span>
          <span className="max-w-[60ch] text-fg">
            {finding.claim}
            <CitationMarkers evidence={finding.evidence} citations={citations} />
          </span>
        </li>
      ))}
    </ul>
  );
}

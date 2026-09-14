"use client";

import Link from "next/link";

import type { ResearchRunSummary, Stance } from "@/lib/types";

const STANCE_COLOR: Record<Stance, string> = {
  BULLISH: "var(--color-bull)",
  BEARISH: "var(--color-bear)",
  NEUTRAL: "var(--color-signal)",
};

/**
 * research_date is a calendar date, not an instant. Passing "2026-09-08"
 * to `new Date` parses it as UTC midnight, which renders as the 7th for
 * anyone behind UTC — so build a local date from the parts instead.
 */
function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function Outcome({ run }: { run: ResearchRunSummary }) {
  if (run.stance) {
    return (
      <span className="flex items-baseline gap-2">
        <span
          className="text-sm capitalize"
          style={{ color: STANCE_COLOR[run.stance] }}
        >
          {run.stance.toLowerCase()}
        </span>
        {run.conviction !== null && (
          <span className="tnum text-xs text-faint">{run.conviction}</span>
        )}
      </span>
    );
  }

  if (run.status === "FAILED") {
    return (
      <span className="text-sm text-bear">
        {run.error ? shortError(run.error) : "Failed"}
      </span>
    );
  }

  if (run.status === "COMPLETE") {
    // Completed before the persistence layer existed, so there's nothing
    // to open. Saying so beats a link to an empty page.
    return <span className="text-sm text-faint">No report stored</span>;
  }

  return <span className="text-sm text-muted">In progress</span>;
}

/**
 * Enough of a failure to recognise it without opening the run.
 *
 * Stored errors are "ExceptionType: raw message", and for API failures the
 * raw part is often a serialised payload whose only readable content is a
 * nested message field. Splitting on the first colon would leave just
 * "BadRequestError", which doesn't distinguish a billing failure from a
 * malformed request — so prefer that inner message when there is one.
 */
function shortError(error: string): string {
  const message = error.match(/'message':\s*'([^']+)'/)?.[1];
  const text = message ?? error;
  const firstLine = text.split("\n")[0];
  return firstLine.length > 72 ? `${firstLine.slice(0, 72)}…` : firstLine;
}

export default function RunHistory({
  runs,
  showTicker = false,
  emptyLabel,
}: {
  runs: ResearchRunSummary[];
  showTicker?: boolean;
  emptyLabel: string;
}) {
  if (runs.length === 0) {
    return <p className="text-sm text-faint">{emptyLabel}</p>;
  }

  return (
    <ul className="border-t border-line-soft">
      {runs.map((run) => {
        const openable = run.has_report || run.status === "FAILED";
        const row = (
          <>
            {showTicker && (
              <span className="tnum w-16 shrink-0 text-sm text-signal">
                {run.ticker}
              </span>
            )}
            <span className="tnum w-28 shrink-0 text-sm text-muted">
              {formatDate(run.research_date)}
            </span>
            <span className="min-w-0 flex-1 truncate">
              <Outcome run={run} />
            </span>
            <span className="tnum shrink-0 text-xs text-faint">
              {run.research_run_id}
            </span>
          </>
        );

        return (
          <li key={run.research_run_id} className="border-b border-line-soft">
            {openable ? (
              <Link
                href={`/research/${run.research_run_id}`}
                className="flex items-baseline gap-4 py-3.5 transition-colors hover:bg-surface"
              >
                {row}
              </Link>
            ) : (
              <div className="flex items-baseline gap-4 py-3.5 opacity-60">
                {row}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

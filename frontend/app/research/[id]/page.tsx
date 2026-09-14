"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import ReportView from "@/components/ReportView";
import { ApiError, getResearchRun, getResearchRunStatus } from "@/lib/api";
import type { ResearchRunDetail, ResearchRunStatus } from "@/lib/types";
import { isTerminal } from "@/lib/types";

const POLL_INTERVAL_MS = 3000;

/**
 * The orchestrator runs Fundamental/Filing/Valuation concurrently and uses
 * the generic RUNNING status for that whole phase (see orchestrator.py's
 * docstring — no single per-agent value is accurate while three are in
 * flight), so this describes what's genuinely known rather than implying a
 * per-agent walk the backend doesn't report.
 */
const STATUS_LABELS: Record<ResearchRunStatus, string> = {
  PENDING: "Queued",
  RUNNING: "Analysts reading, then the debate",
  FUNDAMENTAL_RUNNING: "Reading the fundamentals",
  FILING_RUNNING: "Reading the filings",
  VALUATION_RUNNING: "Valuing the business",
  BULL_RUNNING: "Building the bull case",
  BEAR_RUNNING: "Building the bear case",
  JUDGE_RUNNING: "Judge deliberating",
  COMPLETE: "Complete",
  FAILED: "Failed",
};

/** A run's inputs are snapshotted at run time, so this is a fixed fact
 *  about the report, not a live age. */
function formatVintage(timestamp: string | null): string {
  if (!timestamp) return "unknown";
  return new Date(timestamp).toLocaleDateString();
}

export default function ResearchRunPage() {
  const { id } = useParams<{ id: string }>();
  const runId = Number(id);

  const [status, setStatus] = useState<ResearchRunStatus | null>(null);
  const [detail, setDetail] = useState<ResearchRunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startedAt = useRef(Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!Number.isFinite(runId)) {
      setError("Invalid research run id");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const { status } = await getResearchRunStatus(runId);
        if (cancelled) return;
        setStatus(status);

        if (isTerminal(status)) {
          // Only pull the full payload once, at the end — that's the point
          // of the separate lightweight status endpoint.
          const detail = await getResearchRun(runId);
          if (!cancelled) setDetail(detail);
          return;
        }
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Lost contact with the API");
      }
    }

    poll();
    const ticker = setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAt.current) / 1000)),
      1000,
    );

    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearInterval(ticker);
    };
  }, [runId]);

  const running = status !== null && !isTerminal(status);

  return (
    <main className="mx-auto max-w-4xl px-6 pb-24 pt-12">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
        <Link href="/" className="text-sm text-muted hover:text-fg">
          Search
        </Link>
        <span className="tnum text-xs text-faint">run {runId}</span>
      </div>

      {detail && (
        <div className="mt-6 flex flex-wrap items-baseline gap-x-4">
          <Link
            href={`/companies/${detail.ticker}`}
            className="tnum text-3xl font-medium tracking-tight text-signal hover:underline"
          >
            {detail.ticker}
          </Link>
          {detail.report?.company && (
            <span className="font-display text-2xl text-fg">
              {detail.report.company.name}
            </span>
          )}
        </div>
      )}

      {error && (
        <p className="mt-6 border-l-2 border-bear pl-3 text-sm text-bear">
          {error}
        </p>
      )}

      {running && status && (
        <div className="mt-10 border-l-2 border-signal py-2 pl-5">
          <div className="flex items-center gap-3">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-signal" />
            <span className="text-[15px] text-fg">{STATUS_LABELS[status]}</span>
          </div>
          <p className="tnum mt-1.5 text-xs text-faint">
            {elapsed}s elapsed, checking every {POLL_INTERVAL_MS / 1000}s
          </p>
        </div>
      )}

      {detail?.status === "FAILED" && (
        <div className="mt-10 border-l-2 border-bear py-2 pl-5">
          <p className="font-display text-xl text-bear">This run failed</p>
          <p className="tnum mt-2 max-w-[72ch] text-sm leading-relaxed text-fg">
            {detail.error ?? "No error was recorded."}
          </p>
          {detail.report && (
            <p className="mt-2 text-sm text-muted">
              What the agents finished before it failed is below.
            </p>
          )}
        </div>
      )}

      {detail?.report ? (
        <div className="mt-12">
          <ReportView report={detail.report} />
        </div>
      ) : (
        detail && (
          <p className="mt-10 text-sm text-faint">
            No report was stored for this run.
          </p>
        )
      )}

      {/* The verdict leads; what it was computed from closes. The warning
          that actually changes behaviour — "your data is stale, refresh
          before running" — lives on the company page, before a run starts. */}
      {detail && isTerminal(detail.status) && (
        <section className="mt-14">
          <h2 className="rule-heading">What this was based on</h2>
          <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-3">
            <div>
              <dt className="text-xs text-faint">Share price used</dt>
              <dd className="tnum mt-1 text-sm text-fg">
                {detail.price_at_run !== null
                  ? `$${detail.price_at_run.toFixed(2)}`
                  : "none available"}
                {detail.price_as_of && (
                  <span className="text-faint"> · {detail.price_as_of}</span>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Financials last checked</dt>
              <dd className="tnum mt-1 text-sm text-fg">
                {formatVintage(detail.financials_as_of)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-faint">Filings last checked</dt>
              <dd className="tnum mt-1 text-sm text-fg">
                {formatVintage(detail.filings_as_of)}
              </dd>
            </div>
          </dl>
          <p className="mt-4 max-w-[72ch] text-xs leading-relaxed text-faint">
            These are the inputs as they stood when this run executed, not as
            they are now.
          </p>
        </section>
      )}
    </main>
  );
}

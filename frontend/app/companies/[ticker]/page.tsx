"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import RunHistory from "@/components/RunHistory";
import {
  ApiError,
  getCompany,
  getFilings,
  getFinancials,
  listResearchRuns,
  refreshFinancials,
  startResearch,
  syncFilings,
} from "@/lib/api";
import type { Company, ResearchRunSummary } from "@/lib/types";

interface Readiness {
  metricPeriods: number;
  filings: number;
}

function describeAge(timestamp: string | null): string {
  // Null means no record of a check, which isn't the same as no data:
  // rows ingested before this timestamp existed read as unknown, not never.
  if (!timestamp) return "unknown";
  const days = Math.floor(
    (Date.now() - new Date(timestamp).getTime()) / 86_400_000,
  );
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  return `${days} days ago`;
}

const STALE_AFTER_DAYS = 7;

function isStale(timestamp: string | null): boolean {
  if (!timestamp) return false;
  return Date.now() - new Date(timestamp).getTime() > STALE_AFTER_DAYS * 86_400_000;
}

function SourceRow({
  name,
  count,
  unit,
  ready,
  checked,
  stale,
}: {
  name: string;
  count: number;
  unit: string;
  ready: boolean;
  checked: string;
  stale: boolean;
}) {
  return (
    <div className="flex items-baseline gap-4 border-b border-line-soft py-3">
      <span
        className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
        style={{
          background: ready ? "var(--color-bull)" : "var(--color-bear)",
        }}
        aria-hidden
      />
      <span className="w-36 shrink-0 text-sm text-fg">{name}</span>
      <span className="flex-1 text-sm text-muted">
        <span className="tnum text-fg">{count}</span> {unit}
      </span>
      <span
        className="text-xs"
        style={{ color: stale ? "var(--color-signal)" : "var(--color-faint)" }}
      >
        checked {checked}
      </span>
    </div>
  );
}

export default function CompanyPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const router = useRouter();

  const [company, setCompany] = useState<Company | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [runs, setRuns] = useState<ResearchRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [preparing, setPreparing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [companyData, financials, filings, history] = await Promise.all([
        getCompany(ticker),
        // Note: GET /financials fetches from Alpha Vantage and caches on
        // first call, so this doubles as the "prepare financials" step.
        getFinancials(ticker),
        getFilings(ticker),
        listResearchRuns(ticker),
      ]);
      setCompany(companyData);
      setRuns(history.runs);
      setReadiness({
        metricPeriods: financials.periods.length,
        filings: filings.filings.length,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load company");
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    load();
  }, [load]);

  async function onPrepare() {
    setPreparing(true);
    setError(null);
    try {
      await syncFilings(ticker);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not ingest filings");
    } finally {
      setPreparing(false);
    }
  }

  async function onRefresh() {
    setRefreshing(true);
    setError(null);
    try {
      // Financials first: it's the one that's otherwise permanently
      // frozen, since the plain GET always serves the cache.
      await refreshFinancials(ticker);
      await syncFilings(ticker);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not refresh data");
    } finally {
      setRefreshing(false);
    }
  }

  async function onStartResearch() {
    setStarting(true);
    setError(null);
    try {
      const run = await startResearch(ticker);
      router.push(`/research/${run.research_run_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start research");
      setStarting(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-20 text-sm text-faint">
        Loading {ticker.toUpperCase()}
      </main>
    );
  }

  const hasMetrics = (readiness?.metricPeriods ?? 0) > 0;
  const hasFilings = (readiness?.filings ?? 0) > 0;
  // The Valuation Analyst needs financial metrics (it raises
  // ValuationInputsMissingError without them), so a run would fail outright.
  // Filings are softer — the Filing Analyst just finds nothing.
  const canResearch = hasMetrics;
  const anythingStale =
    isStale(company?.financials_refreshed_at ?? null) ||
    isStale(company?.filings_synced_at ?? null);

  return (
    <main className="mx-auto max-w-3xl px-6 pb-24 pt-12">
      <Link href="/" className="text-sm text-muted hover:text-fg">
        Search
      </Link>

      <div className="mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="tnum text-3xl font-medium tracking-tight text-signal">
          {company?.ticker ?? ticker.toUpperCase()}
        </h1>
        <span className="font-display text-2xl text-fg">{company?.name}</span>
      </div>
      {company && (company.exchange || company.sector || company.industry) && (
        <p className="mt-2 text-sm text-faint">
          {[company.exchange, company.sector, company.industry]
            .filter(Boolean)
            .join(", ")}
        </p>
      )}

      {error && (
        <p className="mt-6 border-l-2 border-bear pl-3 text-sm text-bear">
          {error}
        </p>
      )}

      <section className="mt-12">
        <h2 className="rule-heading">Research inputs</h2>

        <div className="mt-4 border-t border-line-soft">
          <SourceRow
            name="Financial metrics"
            count={readiness?.metricPeriods ?? 0}
            unit="reporting periods"
            ready={hasMetrics}
            checked={describeAge(company?.financials_refreshed_at ?? null)}
            stale={isStale(company?.financials_refreshed_at ?? null)}
          />
          <SourceRow
            name="SEC filings"
            count={readiness?.filings ?? 0}
            unit="ingested"
            ready={hasFilings}
            checked={describeAge(company?.filings_synced_at ?? null)}
            stale={isStale(company?.filings_synced_at ?? null)}
          />
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          {!hasFilings && (
            <button
              onClick={onPrepare}
              disabled={preparing || refreshing}
              className="rounded border border-line px-4 py-2 text-sm text-fg transition-colors hover:border-signal hover:text-signal disabled:opacity-40"
            >
              {preparing ? "Ingesting filings" : "Ingest filings"}
            </button>
          )}
          <button
            onClick={onRefresh}
            disabled={refreshing || preparing}
            className="rounded border border-line px-4 py-2 text-sm text-fg transition-colors hover:border-signal hover:text-signal disabled:opacity-40"
          >
            {refreshing ? "Refreshing" : "Refresh data"}
          </button>
        </div>

        <p className="mt-4 max-w-[68ch] text-xs leading-relaxed text-faint">
          A run analyses whatever is stored here and never fetches on its own,
          apart from the share price, which it pulls fresh each time.
          Refreshing costs about five of Alpha Vantage&apos;s 25 daily requests
          and picks up any newly filed 10-Q or 8-K.
        </p>

        {anythingStale && (
          <p className="mt-3 max-w-[68ch] text-sm text-signal">
            These inputs are more than {STALE_AFTER_DAYS} days old. A run
            started now would analyse them as they are.
          </p>
        )}

        {!hasMetrics && (
          <p className="mt-3 max-w-[68ch] text-sm text-bear">
            No financial metrics, so the valuation has nothing to work from and
            a run would fail. Alpha Vantage may have returned nothing for this
            ticker, or the daily request cap is spent.
          </p>
        )}
      </section>

      <div className="mt-12 border-t border-line pt-8">
        <button
          onClick={onStartResearch}
          disabled={!canResearch || starting}
          className="rounded px-6 py-3 text-[15px] font-medium transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          style={{ background: "var(--color-signal)", color: "var(--color-ink)" }}
        >
          {starting ? "Starting" : "Run research"}
        </button>
        <p className="mt-3 max-w-[60ch] text-xs leading-relaxed text-faint">
          Seven agents read the filings and fundamentals, argue both sides, and
          return a judged verdict. Takes a few minutes and spends real API
          credit.
        </p>
      </div>

      <section className="mt-14">
        <h2 className="rule-heading">Past runs</h2>
        <div className="mt-4">
          <RunHistory
            runs={runs}
            emptyLabel={`No research has been run on ${company?.ticker ?? ticker.toUpperCase()} yet.`}
          />
        </div>
      </section>
    </main>
  );
}

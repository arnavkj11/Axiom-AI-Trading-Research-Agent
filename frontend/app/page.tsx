"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import RunHistory from "@/components/RunHistory";
import {
  addCompany,
  ApiError,
  listResearchRuns,
  lookupRegistrants,
  searchCompanies,
} from "@/lib/api";
import type {
  Company,
  CompanyCandidate,
  ResearchRunSummary,
} from "@/lib/types";

export default function SearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [searchedFor, setSearchedFor] = useState("");
  const [results, setResults] = useState<Company[] | null>(null);
  const [candidates, setCandidates] = useState<CompanyCandidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<ResearchRunSummary[]>([]);

  // Recent runs across every company, so a past report is reachable even
  // when you can't remember which ticker it was for.
  useEffect(() => {
    listResearchRuns(undefined, 8)
      .then(({ runs }) => setRecentRuns(runs))
      .catch(() => setRecentRuns([]));
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    setSearching(true);
    setError(null);
    setCandidates(null);
    try {
      const { results } = await searchCompanies(trimmed);
      setResults(results);
      setSearchedFor(trimmed);

      if (results.length === 0) {
        const { candidates } = await lookupRegistrants(trimmed);
        setCandidates(candidates);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  async function onAddCompany(ticker: string) {
    setAdding(ticker);
    setError(null);
    try {
      const company = await addCompany(ticker);
      router.push(`/companies/${company.ticker}`);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not add that company",
      );
      setAdding(null);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 pb-24 pt-20">
      <h1 className="text-4xl leading-[1.15] text-fg sm:text-5xl">
        A bull and a bear argue.
        <br />
        <span className="text-muted">A judge rules.</span>
      </h1>
      <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-muted">
        Pick a public company and Axiom runs seven agents over its filings and
        fundamentals, stages a debate between the strongest case for and
        against, and returns a verdict where every claim traces back to a
        number or a quote.
      </p>

      <form onSubmit={onSubmit} className="mt-10">
        <label htmlFor="company-search" className="sr-only">
          Search by ticker or company name
        </label>
        <div className="flex items-stretch gap-px overflow-hidden rounded border border-line bg-surface focus-within:border-signal/60">
          <input
            id="company-search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ticker or company name"
            className="flex-1 bg-transparent px-4 py-3.5 text-[15px] text-fg placeholder:text-faint focus:outline-none"
          />
          <button
            type="submit"
            disabled={searching || !query.trim()}
            className="shrink-0 px-5 text-sm font-medium text-ink transition-colors disabled:cursor-not-allowed"
            style={{
              background: query.trim() && !searching ? "#e8b24c" : "#24343d",
              color: query.trim() && !searching ? "#0e1418" : "#5d717c",
            }}
          >
            {searching ? "Searching" : "Search"}
          </button>
        </div>
      </form>

      {error && (
        <p className="mt-5 border-l-2 border-bear pl-3 text-sm text-bear">
          {error}
        </p>
      )}

      {results && results.length > 0 && (
        <ul className="mt-10 border-t border-line-soft">
          {results.map((company) => (
            <li key={company.id}>
              <Link
                href={`/companies/${company.ticker}`}
                className="flex items-baseline gap-4 border-b border-line-soft px-1 py-4 transition-colors hover:bg-surface"
              >
                <span className="tnum w-16 shrink-0 text-sm font-medium text-signal">
                  {company.ticker}
                </span>
                <span className="flex-1 text-[15px] text-fg">
                  {company.name}
                </span>
                {company.sector && (
                  <span className="hidden text-xs text-faint sm:block">
                    {company.sector}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {/* Shown until a search happens: what a run actually does. This is a
          real sequence — three analysts read, two argue, one rules — so it's
          drawn as one, and it doubles as an explanation of why the verdict
          is worth trusting more than a single model's opinion. */}
      {!results && recentRuns.length > 0 && (
        <section className="mt-14">
          <h2 className="rule-heading">Recent runs</h2>
          <div className="mt-4">
            <RunHistory runs={recentRuns} showTicker emptyLabel="" />
          </div>
        </section>
      )}

      {!results && !error && (
        <section className="mt-16 border-t border-line-soft pt-10">
          <h2 className="rule-heading">What a run does</h2>
          <ol className="mt-6 space-y-5">
            <li className="flex gap-5">
              <span className="mt-2 h-px w-8 shrink-0 bg-line" aria-hidden />
              <p className="max-w-[58ch] text-sm leading-relaxed text-muted">
                <span className="text-fg">Three analysts read.</span> One works
                the fundamentals, one searches the SEC filings, one values the
                business with a discounted cash flow. Every finding they make
                has to cite a specific number or passage.
              </p>
            </li>
            <li className="flex gap-5">
              <span
                className="mt-2 h-px w-8 shrink-0"
                style={{
                  background:
                    "linear-gradient(90deg, var(--color-bull), var(--color-bear))",
                }}
                aria-hidden
              />
              <p className="max-w-[58ch] text-sm leading-relaxed text-muted">
                <span className="text-fg">Two of them argue.</span> A bull and a
                bear each build the strongest case they can from that shared
                evidence, then get exactly one rebuttal apiece. Neither can
                invent a fact the analysts didn&apos;t find.
              </p>
            </li>
            <li className="flex gap-5">
              <span
                className="mt-2 h-px w-8 shrink-0"
                style={{ background: "var(--color-signal)" }}
                aria-hidden
              />
              <p className="max-w-[58ch] text-sm leading-relaxed text-muted">
                <span className="text-fg">A judge rules.</span> It weighs the
                exchange and returns a stance, a conviction score, and a
                synthesis — with the fair value set against what the stock
                actually costs.
              </p>
            </li>
          </ol>
        </section>
      )}

      {results && results.length === 0 && (
        <div className="mt-10">
          {candidates && candidates.length > 0 ? (
            <>
              <p className="text-sm text-muted">
                Not in your database yet. These match on SEC&apos;s registrant
                list:
              </p>
              <ul className="mt-4 border-t border-line-soft">
                {candidates.map((candidate) => (
                  <li
                    key={candidate.ticker}
                    className="flex items-center gap-4 border-b border-line-soft py-3.5"
                  >
                    <span className="tnum w-16 shrink-0 text-sm font-medium text-signal">
                      {candidate.ticker}
                    </span>
                    <span className="flex-1 text-[15px] text-fg">
                      {candidate.name}
                    </span>
                    {candidate.in_database ? (
                      <Link
                        href={`/companies/${candidate.ticker}`}
                        className="text-sm text-muted hover:text-fg"
                      >
                        Open
                      </Link>
                    ) : (
                      <button
                        onClick={() => onAddCompany(candidate.ticker)}
                        disabled={adding !== null}
                        className="rounded border border-line px-3 py-1.5 text-sm text-fg transition-colors hover:border-signal hover:text-signal disabled:opacity-40"
                      >
                        {adding === candidate.ticker ? "Adding" : "Add"}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-muted">
              Nothing matched &ldquo;{searchedFor}&rdquo;, in your database or on
              SEC&apos;s registrant list. Only SEC-registered public companies
              can be researched.
            </p>
          )}
        </div>
      )}
    </main>
  );
}

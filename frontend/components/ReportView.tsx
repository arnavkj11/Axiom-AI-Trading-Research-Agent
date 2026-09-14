"use client";

import { buildCitationIndex } from "@/lib/citations";
import type {
  DebateCase,
  Recommendation,
  RecommendationAction,
  ResearchState,
  Stance,
  ValuationOutput,
} from "@/lib/types";
import { FindingList } from "./Citations";
import SourcesPanel from "./SourcesPanel";

const STANCE_COLOR: Record<Stance, string> = {
  BULLISH: "var(--color-bull)",
  BEARISH: "var(--color-bear)",
  NEUTRAL: "var(--color-signal)",
};

function Section({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`mt-14 ${className}`}>
      <h2 className="rule-heading">{title}</h2>
      <div className="mt-5">{children}</div>
    </section>
  );
}

/**
 * The verdict as a position between two poles rather than a badge.
 * Conviction is a magnitude on that axis, so showing it as one makes the
 * shape of the call readable before any of the prose is.
 */
function VerdictScale({ report }: { report: ResearchState }) {
  const verdict = report.judge_verdict;
  if (!verdict) return null;

  // Bearish sits left, bullish right; conviction is distance from centre.
  const half = verdict.conviction / 2;
  const position =
    verdict.stance === "BULLISH"
      ? 50 + half
      : verdict.stance === "BEARISH"
        ? 50 - half
        : 50;
  const color = STANCE_COLOR[verdict.stance];

  return (
    <div className="settle">
      <div className="flex items-baseline gap-4">
        <span
          className="font-display text-5xl leading-none sm:text-6xl"
          style={{ color }}
        >
          {verdict.stance.toLowerCase()}
        </span>
        <span className="tnum text-sm text-muted">
          conviction {verdict.conviction}
        </span>
      </div>

      <div className="mt-7">
        <div className="relative h-px w-full bg-line">
          {/* Centre tick: the neutral line the verdict is measured from. */}
          <span className="absolute left-1/2 top-1/2 h-2.5 w-px -translate-x-1/2 -translate-y-1/2 bg-line" />
          <span
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ left: `${position}%`, background: color }}
          />
          <span
            className="absolute top-1/2 h-px -translate-y-1/2"
            style={
              position >= 50
                ? { left: "50%", width: `${position - 50}%`, background: color }
                : { left: `${position}%`, width: `${50 - position}%`, background: color }
            }
          />
        </div>
        <div className="mt-2.5 flex justify-between text-xs text-faint">
          <span>bearish</span>
          <span>bullish</span>
        </div>
      </div>

      {report.recommendation && (
        <ActionCall recommendation={report.recommendation} />
      )}

      <p className="mt-8 max-w-[68ch] whitespace-pre-line font-display text-[19px] leading-[1.65] text-fg">
        {verdict.synthesis}
      </p>
    </div>
  );
}

const ACTION_COLOR: Record<RecommendationAction, string> = {
  BUY: "var(--color-bull)",
  SELL: "var(--color-bear)",
  HOLD: "var(--color-signal)",
  NOT_RATED: "var(--color-faint)",
};

/**
 * The action, with the arithmetic that produced it shown alongside.
 * Deliberately not presented as an oracle: a reader who can't evaluate the
 * research themselves should still be able to see it's a rule over two
 * numbers, and what would have to change to flip it.
 */
function ActionCall({ recommendation }: { recommendation: Recommendation }) {
  const color = ACTION_COLOR[recommendation.action];
  const label =
    recommendation.action === "NOT_RATED" ? "Not rated" : recommendation.action;

  return (
    <div className="mt-8 border-l-2 py-3 pl-5" style={{ borderColor: color }}>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span
          className="font-display text-2xl leading-none"
          style={{ color }}
        >
          {label}
        </span>
        <span className="text-xs text-faint">
          computed from the verdict and the price, not by the model
        </span>
      </div>
      <p className="mt-2.5 max-w-[70ch] text-sm leading-relaxed text-muted">
        {recommendation.rationale}
      </p>
    </div>
  );
}

/**
 * Fair values laid on a number line against what the stock actually costs.
 * A table of fair values leaves the reader to do the comparison; placing
 * them on an axis with the price makes cheap-or-expensive the first thing
 * you see, which is the question a non-specialist actually has.
 */
function ValueLine({ valuation }: { valuation: ValuationOutput }) {
  const price = valuation.current_price;
  const values = valuation.scenarios.map((s) => s.fair_value_per_share);
  const points = price !== null ? [...values, price] : values;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  // Inset so end markers and their labels stay on the canvas.
  const at = (value: number) => 6 + ((value - min) / span) * 88;

  return (
    <div>
      {price !== null ? (
        <p className="text-sm text-muted">
          Trading at{" "}
          <span className="tnum text-fg">${price.toFixed(2)}</span>. Each
          scenario&apos;s fair value sits above or below that.
        </p>
      ) : (
        <p className="text-sm text-bear">
          No market price for this run, so these fair values have nothing to be
          compared against.
        </p>
      )}

      {/* Hidden on the narrowest screens: the axis needs horizontal room
          for its labels, and the table below carries the same numbers. */}
      <div className="relative mt-10 mb-2 hidden h-24 sm:block">
        <div className="absolute left-0 right-0 top-11 h-px bg-line" />

        {valuation.scenarios.map((scenario) => (
          <div
            key={scenario.scenario}
            className="absolute top-0 -translate-x-1/2 text-center"
            style={{ left: `${at(scenario.fair_value_per_share)}%` }}
          >
            <div className="tnum text-[13px] text-fg">
              ${scenario.fair_value_per_share.toFixed(2)}
            </div>
            <div className="mt-1 text-[11px] text-faint">
              {scenario.scenario}
            </div>
            <div className="mx-auto mt-1.5 h-3 w-px bg-faint" />
          </div>
        ))}

        {price !== null && (
          <div
            className="absolute top-[42px] -translate-x-1/2"
            style={{ left: `${at(price)}%` }}
          >
            <div
              className="mx-auto h-5 w-0.5"
              style={{ background: "var(--color-signal)" }}
            />
            <div className="mt-1.5 whitespace-nowrap text-center">
              <div className="tnum text-[13px] text-signal">
                ${price.toFixed(2)}
              </div>
              <div className="text-[11px] text-faint">price</div>
            </div>
          </div>
        )}
      </div>

      <div className="mt-8 overflow-x-auto">
      <table className="w-full min-w-[34rem] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs font-normal text-faint">
            <th className="py-2 pr-4 font-normal">Scenario</th>
            <th className="py-2 pr-4 font-normal">Fair value</th>
            <th className="py-2 pr-4 font-normal">Against price</th>
            <th className="py-2 pr-4 font-normal">Growth</th>
            <th className="py-2 font-normal">Discount</th>
          </tr>
        </thead>
        <tbody>
          {valuation.scenarios.map((scenario) => (
            <tr key={scenario.scenario} className="border-b border-line-soft">
              <td className="py-2.5 pr-4 capitalize text-fg">
                {scenario.scenario}
              </td>
              <td className="tnum py-2.5 pr-4 text-fg">
                ${scenario.fair_value_per_share.toFixed(2)}
              </td>
              <td
                className="tnum py-2.5 pr-4"
                style={{
                  color:
                    scenario.upside_pct === null
                      ? "var(--color-faint)"
                      : scenario.upside_pct >= 0
                        ? "var(--color-bull)"
                        : "var(--color-bear)",
                }}
              >
                {scenario.upside_pct === null
                  ? "—"
                  : `${scenario.upside_pct >= 0 ? "+" : ""}${(
                      scenario.upside_pct * 100
                    ).toFixed(1)}%`}
              </td>
              <td className="tnum py-2.5 pr-4 text-muted">
                {(scenario.assumptions.growth_rate * 100).toFixed(1)}%
              </td>
              <td className="tnum py-2.5 text-muted">
                {(scenario.assumptions.discount_rate * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      <p className="mt-4 text-xs leading-relaxed text-faint">
        Against price is{" "}
        <span className="tnum text-muted">(fair value − price) ÷ price</span>,
        computed in Python rather than by the model. The analyst chose these
        assumptions without being shown the price, so the valuation is free to
        disagree with the market.
      </p>

      {valuation.commentary && (
        <p className="mt-4 max-w-[68ch] text-sm leading-relaxed text-muted">
          {valuation.commentary}
        </p>
      )}
    </div>
  );
}

function CaseColumn({
  side,
  summary,
  debateCase,
  citations,
}: {
  side: "bull" | "bear";
  summary: string | undefined;
  debateCase: DebateCase | null;
  citations: ReturnType<typeof buildCitationIndex>;
}) {
  const color = side === "bull" ? "var(--color-bull)" : "var(--color-bear)";

  if (!debateCase) {
    return (
      <div className="border-l pl-5" style={{ borderColor: "var(--color-line)" }}>
        <h3 className="font-display text-xl capitalize text-muted">{side}</h3>
        <p className="mt-2 text-sm text-faint">No case was produced.</p>
      </div>
    );
  }

  return (
    <div className="border-l pl-5" style={{ borderColor: color }}>
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-display text-xl capitalize" style={{ color }}>
          {side}
        </h3>
        <span className="tnum text-xs text-faint">
          confidence {debateCase.confidence.toFixed(2)}
        </span>
      </div>

      <p className="mt-3 max-w-[62ch] font-display text-[17px] leading-[1.6] text-fg">
        {debateCase.thesis}
      </p>

      {summary && (
        <p className="mt-3 max-w-[62ch] text-sm leading-relaxed text-muted">
          {summary}
        </p>
      )}

      <div className="mt-5">
        <FindingList findings={debateCase.findings} citations={citations} />
      </div>

      {debateCase.rebuttal ? (
        <div className="mt-6 border-t border-line-soft pt-4">
          <p className="text-xs text-faint">Rebuttal</p>
          <p className="mt-2 max-w-[62ch] text-sm leading-relaxed text-fg">
            {debateCase.rebuttal}
          </p>
          <div className="mt-3">
            <FindingList
              findings={debateCase.rebuttal_findings}
              citations={citations}
              emptyLabel="No new evidence cited in the rebuttal."
            />
          </div>
        </div>
      ) : (
        <p className="mt-6 border-t border-line-soft pt-4 text-sm text-faint">
          No rebuttal recorded.
        </p>
      )}
    </div>
  );
}

export default function ReportView({ report }: { report: ResearchState }) {
  const citations = buildCitationIndex(report);
  const verdict = report.judge_verdict;

  return (
    <div>
      <VerdictScale report={report} />

      {report.valuation_output && (
        <Section title="Value against price">
          <ValueLine valuation={report.valuation_output} />
        </Section>
      )}

      <Section title="The debate">
        <div className="grid gap-10 lg:grid-cols-2">
          <CaseColumn
            side="bull"
            summary={verdict?.bull_summary}
            debateCase={report.bull_case}
            citations={citations}
          />
          <CaseColumn
            side="bear"
            summary={verdict?.bear_summary}
            debateCase={report.bear_case}
            citations={citations}
          />
        </div>

        {verdict?.rebuttal_summary && (
          <div className="mt-10 border-l-2 border-signal bg-surface/60 py-4 pl-5 pr-4">
            <p className="text-xs text-faint">How the judge read the round</p>
            <p className="mt-2 max-w-[72ch] font-display text-[16px] leading-[1.65] text-fg">
              {verdict.rebuttal_summary}
            </p>
          </div>
        )}
      </Section>

      {verdict && (
        <Section title="What it turns on">
          <div className="grid gap-8 sm:grid-cols-3">
            <div>
              <p className="mb-3 text-xs text-faint">Key findings</p>
              <FindingList findings={verdict.key_findings} citations={citations} />
            </div>
            <div>
              <p className="mb-3 text-xs text-faint">Risks</p>
              <FindingList findings={verdict.risks} citations={citations} />
            </div>
            <div>
              <p className="mb-3 text-xs text-faint">Catalysts</p>
              <FindingList findings={verdict.catalysts} citations={citations} />
            </div>
          </div>
        </Section>
      )}

      <Section title={`Evidence (${citations.sources.length})`}>
        <p className="mb-4 max-w-[68ch] text-sm text-muted">
          Every numbered marker above points here. Open one to see the metric,
          filing passage, or calculation it rests on.
        </p>
        <SourcesPanel citations={citations} />
      </Section>
    </div>
  );
}

"""BUY / SELL / HOLD, derived deterministically from a finished run.

Not an eighth agent, on purpose. The Judge has already read everything;
a model asked to re-read its verdict would add a call, latency, and drift
without adding evidence. What's left is arithmetic over three numbers plus
a policy about where the thresholds sit — and policy belongs in code,
where it is explicit, testable, and identical on every run. This is the
one output that tells someone to move money, so determinism matters more
here than anywhere else in the pipeline (CLAUDE.md Rule 1).

The thresholds below are a product decision, not a tuned parameter. They
were set against a handful of runs and self-reported conviction scores
that have never been calibrated against outcomes — nothing here is
backtested. Treat them as a starting position to revisit once there are
enough runs to say anything, and note that every recommendation carries
the thresholds it was computed under, so stored ones stay interpretable
if these change.
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.agents.schemas import JudgeVerdict, Stance, ValuationOutput

# Conviction is 0-100 and self-reported. 60 sits above the middle of the
# range observed so far without demanding near-certainty.
MIN_CONVICTION = 60

# The DCF is deliberately crude — one FCF base, a fixed growth rate, five
# years — so its error bars are wide. Below roughly this much, a gap
# between fair value and price is model noise rather than signal.
MIN_UPSIDE = 0.20

# Margin of safety: never say buy when the run's own pessimistic scenario
# implies losing this much. Applies to BUY only; as a condition on exiting
# a position it would make no sense.
MAX_BEAR_DOWNSIDE = -0.30


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    # Distinct from HOLD: we could not judge, rather than judged and chose
    # to sit still. Collapsing the two would present an absence of analysis
    # as a considered position.
    NOT_RATED = "NOT_RATED"


class Recommendation(BaseModel):
    """An action plus everything needed to check the arithmetic yourself."""

    action: Action
    stance: Stance | None = None
    conviction: int | None = None
    base_upside_pct: float | None = None
    bear_upside_pct: float | None = None
    thresholds: dict[str, float] = Field(default_factory=dict)
    rationale: str


def _thresholds() -> dict[str, float]:
    return {
        "min_conviction": float(MIN_CONVICTION),
        "min_upside_pct": MIN_UPSIDE,
        "max_bear_downside_pct": MAX_BEAR_DOWNSIDE,
    }


def _upside(valuation: ValuationOutput | None, scenario: str) -> float | None:
    if valuation is None:
        return None
    for candidate in valuation.scenarios:
        if candidate.scenario == scenario:
            return candidate.upside_pct
    return None


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def recommend(
    verdict: JudgeVerdict | None, valuation: ValuationOutput | None
) -> Recommendation:
    """Translate a finished run into an action.

    HOLD is the default: it takes a clear stance, real conviction, and a
    gap wide enough to outrun the model's own error to justify anything
    else.
    """
    base_upside = _upside(valuation, "base")
    bear_upside = _upside(valuation, "bear")

    if verdict is None or base_upside is None:
        missing = "no verdict was produced" if verdict is None else "no market price was available"
        return Recommendation(
            action=Action.NOT_RATED,
            stance=verdict.stance if verdict else None,
            conviction=verdict.conviction if verdict else None,
            thresholds=_thresholds(),
            rationale=(
                f"Not rated: {missing}, so value could not be weighed against price."
            ),
        )

    context = {
        "stance": verdict.stance,
        "conviction": verdict.conviction,
        "base_upside_pct": base_upside,
        "bear_upside_pct": bear_upside,
        "thresholds": _thresholds(),
    }
    action, rationale = _decide(verdict, base_upside, bear_upside)
    return Recommendation(action=action, rationale=rationale, **context)


def _decide(
    verdict: JudgeVerdict, base_upside: float, bear_upside: float | None
) -> tuple[Action, str]:
    stance, conviction = verdict.stance, verdict.conviction
    convinced = conviction >= MIN_CONVICTION

    if stance is Stance.NEUTRAL:
        return Action.HOLD, (
            f"Hold: the judge reached no directional call (conviction {conviction}). "
            f"The base case sits {_percent(base_upside)} against the market price, but a "
            "recommendation never overrules the verdict it comes from."
        )

    if stance is Stance.BULLISH:
        if not convinced:
            return Action.HOLD, (
                f"Hold: bullish, but conviction {conviction} is below {MIN_CONVICTION}, so the "
                f"debate did not settle firmly enough to act on — even with the base case "
                f"{_percent(base_upside)} against the price."
            )
        if base_upside < MIN_UPSIDE:
            return Action.HOLD, (
                f"Hold: bullish with conviction {conviction}, but the base case is only "
                f"{_percent(base_upside)} against the market price, short of the "
                f"{_percent(MIN_UPSIDE)} needed to clear this DCF's own margin of error. "
                "A good business already priced accordingly."
            )
        if bear_upside is not None and bear_upside < MAX_BEAR_DOWNSIDE:
            return Action.HOLD, (
                f"Hold: bullish with conviction {conviction} and {_percent(base_upside)} base-case "
                f"upside, but the bear scenario implies {_percent(bear_upside)} — worse than the "
                f"{_percent(MAX_BEAR_DOWNSIDE)} floor. Too little margin of safety to call a buy."
            )
        if bear_upside is None:
            return Action.HOLD, (
                "Hold: bullish and cheap on the base case, but no bear scenario was available "
                "to check the downside against."
            )
        return Action.BUY, (
            f"Buy: bullish with conviction {conviction} (at or above {MIN_CONVICTION}), the base "
            f"case {_percent(base_upside)} above the market price (at or above "
            f"{_percent(MIN_UPSIDE)}), and the bear scenario at {_percent(bear_upside)}, within "
            f"the {_percent(MAX_BEAR_DOWNSIDE)} floor."
        )

    # Bearish.
    if not convinced:
        return Action.HOLD, (
            f"Hold: bearish, but conviction {conviction} is below {MIN_CONVICTION} — not settled "
            "enough to act on."
        )
    if base_upside > -MIN_UPSIDE:
        return Action.HOLD, (
            f"Hold: bearish with conviction {conviction}, but the base case is "
            f"{_percent(base_upside)} against the market price, short of the "
            f"{_percent(-MIN_UPSIDE)} overvaluation that would justify selling."
        )
    return Action.SELL, (
        f"Sell: bearish with conviction {conviction} (at or above {MIN_CONVICTION}) and the base "
        f"case {_percent(base_upside)} against the market price, beyond the "
        f"{_percent(-MIN_UPSIDE)} threshold."
    )

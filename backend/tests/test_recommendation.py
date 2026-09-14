"""The BUY/SELL/HOLD rule.

Deliberately a pure function over data the run already produced, not
another LLM call: this is the one output that tells someone to move money,
so the same verdict and the same price must always yield the same
recommendation. Thresholds are an explicit product decision, visible in
the output rather than buried in a prompt.
"""

import pytest

from app.agents.schemas import (
    JudgeVerdict,
    ScenarioValuation,
    Stance,
    ValuationOutput,
)
from app.research.recommendation import (
    MAX_BEAR_DOWNSIDE,
    MIN_CONVICTION,
    MIN_UPSIDE,
    Action,
    recommend,
)


def _verdict(stance: Stance, conviction: int) -> JudgeVerdict:
    return JudgeVerdict(
        stance=stance,
        conviction=conviction,
        synthesis="s",
        bull_summary="b",
        bear_summary="b",
        rebuttal_summary="r",
    )


def _valuation(base_upside: float | None, bear_upside: float | None = 0.0) -> ValuationOutput:
    def scenario(name, upside):
        return ScenarioValuation(
            scenario=name,
            fair_value_per_share=100.0,
            assumptions={"growth_rate": 0.05},
            upside_pct=upside,
        )

    return ValuationOutput(
        method="dcf_scenario",
        scenarios=[
            scenario("bear", bear_upside),
            scenario("base", base_upside),
            scenario("bull", 1.0 if base_upside is not None else None),
        ],
        current_price=100.0 if base_upside is not None else None,
        commentary="c",
    )


# --- The three actions ------------------------------------------------


def test_bullish_with_conviction_and_upside_is_a_buy():
    result = recommend(_verdict(Stance.BULLISH, 70), _valuation(0.35))

    assert result.action is Action.BUY


def test_bearish_with_conviction_and_downside_is_a_sell():
    result = recommend(_verdict(Stance.BEARISH, 70), _valuation(-0.35, bear_upside=-0.6))

    assert result.action is Action.SELL


def test_neutral_always_holds_however_extreme_the_gap():
    # The judge saw the whole debate and declined to call it; the rule
    # never overrules its own verdict on one number. This is NVDA's case:
    # a great business the DCF says is drastically overpriced.
    result = recommend(_verdict(Stance.NEUTRAL, 58), _valuation(-0.89, bear_upside=-0.94))

    assert result.action is Action.HOLD


# --- Each condition failing independently -----------------------------


def test_high_conviction_but_thin_upside_holds():
    # A good business already fairly priced.
    result = recommend(_verdict(Stance.BULLISH, 90), _valuation(0.04))

    assert result.action is Action.HOLD


def test_large_upside_but_low_conviction_holds():
    # Looks cheap, but the debate never resolved.
    result = recommend(_verdict(Stance.BULLISH, 35), _valuation(0.90))

    assert result.action is Action.HOLD


def test_bearish_with_upside_holds_because_the_signals_disagree():
    result = recommend(_verdict(Stance.BEARISH, 80), _valuation(0.30))

    assert result.action is Action.HOLD


def test_bullish_with_downside_holds_because_the_signals_disagree():
    result = recommend(_verdict(Stance.BULLISH, 80), _valuation(-0.30))

    assert result.action is Action.HOLD


# --- Margin of safety -------------------------------------------------


def test_buy_is_withheld_when_the_bear_case_is_catastrophic():
    # Everything else qualifies, but the run's own pessimistic scenario
    # implies losing most of the position.
    result = recommend(_verdict(Stance.BULLISH, 80), _valuation(0.50, bear_upside=-0.75))

    assert result.action is Action.HOLD
    assert "bear" in result.rationale.lower()


def test_buy_survives_a_merely_uncomfortable_bear_case():
    result = recommend(_verdict(Stance.BULLISH, 80), _valuation(0.50, bear_upside=-0.10))

    assert result.action is Action.BUY


def test_sell_does_not_require_a_bear_floor():
    # The floor is a margin-of-safety guard on buying; it makes no sense
    # as a condition on exiting.
    result = recommend(_verdict(Stance.BEARISH, 70), _valuation(-0.40, bear_upside=-0.95))

    assert result.action is Action.SELL


# --- Boundaries -------------------------------------------------------


def test_thresholds_are_inclusive_at_the_boundary():
    exactly = recommend(
        _verdict(Stance.BULLISH, MIN_CONVICTION),
        _valuation(MIN_UPSIDE, bear_upside=MAX_BEAR_DOWNSIDE),
    )

    assert exactly.action is Action.BUY


def test_just_below_the_conviction_threshold_holds():
    result = recommend(_verdict(Stance.BULLISH, MIN_CONVICTION - 1), _valuation(0.50))

    assert result.action is Action.HOLD


def test_just_below_the_upside_threshold_holds():
    result = recommend(_verdict(Stance.BULLISH, 80), _valuation(MIN_UPSIDE - 0.001))

    assert result.action is Action.HOLD


# --- Not rated --------------------------------------------------------


def test_no_price_is_not_rated_rather_than_hold():
    # HOLD would present an absence of analysis as a considered position.
    result = recommend(_verdict(Stance.BULLISH, 80), _valuation(None))

    assert result.action is Action.NOT_RATED
    assert result.base_upside_pct is None


def test_missing_verdict_is_not_rated():
    result = recommend(None, _valuation(0.50))

    assert result.action is Action.NOT_RATED


def test_missing_valuation_is_not_rated():
    result = recommend(_verdict(Stance.BULLISH, 80), None)

    assert result.action is Action.NOT_RATED


# --- Self-describing output -------------------------------------------


def test_recommendation_carries_the_inputs_and_thresholds_it_used():
    # So a reader sees the formula rather than an oracle, and so a stored
    # recommendation stays interpretable if the thresholds later change.
    result = recommend(_verdict(Stance.BULLISH, 64), _valuation(0.35, bear_upside=-0.05))

    assert result.stance is Stance.BULLISH
    assert result.conviction == 64
    assert result.base_upside_pct == pytest.approx(0.35)
    assert result.bear_upside_pct == pytest.approx(-0.05)
    assert result.thresholds["min_conviction"] == MIN_CONVICTION
    assert result.thresholds["min_upside_pct"] == MIN_UPSIDE
    assert result.thresholds["max_bear_downside_pct"] == MAX_BEAR_DOWNSIDE


def test_rationale_explains_a_buy_in_plain_terms():
    result = recommend(_verdict(Stance.BULLISH, 72), _valuation(0.35, bear_upside=-0.05))

    assert "72" in result.rationale
    assert "35" in result.rationale or "35.0" in result.rationale


def test_rationale_shows_the_comparison_that_blocked_the_call():
    result = recommend(_verdict(Stance.BULLISH, 90), _valuation(0.04))

    # The reader should be able to see *why* — both sides of the failed
    # comparison, so it's the upside that fell short and not the
    # conviction. Asserting the numbers rather than the phrasing keeps this
    # about substance instead of wording.
    assert "4.0%" in result.rationale
    assert "20.0%" in result.rationale

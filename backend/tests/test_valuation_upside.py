"""Upside/downside of each DCF scenario against the market price.

CLAUDE.md Rule 1: this is arithmetic, so Python computes it and the model
never does. It's also the number the whole point of the valuation hangs
on — a $47 fair value means nothing until you know the stock costs $180.
"""

import pytest

from app.valuation.calculations import DCFAssumptions, run_scenario_analysis

ASSUMPTIONS = {
    "bear_assumptions": DCFAssumptions(
        growth_rate=0.03, years=5, discount_rate=0.10, terminal_growth_rate=0.02
    ),
    "base_assumptions": DCFAssumptions(
        growth_rate=0.06, years=5, discount_rate=0.09, terminal_growth_rate=0.025
    ),
    "bull_assumptions": DCFAssumptions(
        growth_rate=0.09, years=5, discount_rate=0.08, terminal_growth_rate=0.03
    ),
}


def _analysis(current_price=None):
    return run_scenario_analysis(
        base_fcf=100.0,
        shares_outstanding=10.0,
        research_run_id=1,
        current_price=current_price,
        **ASSUMPTIONS,
    )


def test_upside_is_none_when_no_price_is_available():
    # A quote failure must not invent an upside number.
    for scenario in _analysis().scenarios:
        assert scenario.upside_pct is None


def test_upside_is_computed_against_the_market_price():
    output = _analysis(current_price=100.0)

    for scenario in output.scenarios:
        expected = (scenario.fair_value_per_share - 100.0) / 100.0
        assert scenario.upside_pct == pytest.approx(expected)


def test_a_fair_value_above_the_price_reads_as_positive_upside():
    output = _analysis(current_price=1.0)  # far below any fair value here

    assert all(s.upside_pct > 0 for s in output.scenarios)


def test_a_fair_value_below_the_price_reads_as_negative_upside():
    output = _analysis(current_price=1_000_000.0)

    assert all(s.upside_pct < 0 for s in output.scenarios)


def test_price_is_carried_on_the_output():
    assert _analysis(current_price=180.42).current_price == 180.42


def test_upside_is_citable_as_valuation_evidence():
    # Bull/Bear/Judge argue from price ("trades 30% below base case"), and
    # every material claim has to cite evidence. Upside is an output field
    # of run_scenario_analysis, so it cites as valuation output — no new
    # Evidence variant needed, and the price it was computed against
    # travels with it.
    output = _analysis(current_price=100.0)

    upside_evidence = [e for e in output.evidence if e.output_field.endswith("upside_pct")]
    assert len(upside_evidence) == 3
    assert all(e.assumptions["current_price"] == 100.0 for e in upside_evidence)


def test_no_upside_evidence_without_a_price():
    output = _analysis()

    assert not [e for e in output.evidence if e.output_field.endswith("upside_pct")]


def test_commentary_mentions_the_price_when_known():
    assert "180.42" in _analysis(current_price=180.42).commentary


def test_zero_price_does_not_blow_up():
    # Defensive: a bad feed shouldn't crash a whole research run on a
    # division by zero.
    for scenario in _analysis(current_price=0.0).scenarios:
        assert scenario.upside_pct is None

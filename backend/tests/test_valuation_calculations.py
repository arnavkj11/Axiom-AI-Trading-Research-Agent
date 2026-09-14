import pytest

from app.valuation.calculations import (
    DCFAssumptions,
    calculate_pe_multiple,
    run_dcf,
    run_scenario_analysis,
)


def test_run_dcf_with_growth_rate_equal_to_discount_rate():
    # When growth == discount rate, each year's discounted FCF collapses to
    # base_fcf (the (1+g)^t / (1+r)^t factors cancel), making this case
    # hand-verifiable: PV of 5 years of FCF = 500, PV of terminal value =
    # 1471.65..., enterprise value / 1000 shares = 1.9714285714285718.
    fair_value = run_dcf(
        base_fcf=100.0,
        shares_outstanding=1000.0,
        assumptions=DCFAssumptions(
            growth_rate=0.10,
            years=5,
            discount_rate=0.10,
            terminal_growth_rate=0.03,
        ),
    )
    assert fair_value == pytest.approx(1.9714285714285718)


def test_run_dcf_adds_net_cash_to_enterprise_value():
    fair_value = run_dcf(
        base_fcf=50.0,
        shares_outstanding=200.0,
        assumptions=DCFAssumptions(
            growth_rate=0.05,
            years=3,
            discount_rate=0.08,
            terminal_growth_rate=0.02,
        ),
        net_cash=500.0,
    )
    assert fair_value == pytest.approx(7.114679783950617)


def test_run_dcf_rejects_terminal_growth_at_or_above_discount_rate():
    with pytest.raises(ValueError):
        run_dcf(
            base_fcf=100.0,
            shares_outstanding=1000.0,
            assumptions=DCFAssumptions(
                growth_rate=0.10,
                years=5,
                discount_rate=0.05,
                terminal_growth_rate=0.05,
            ),
        )


def test_calculate_pe_multiple_multiplies_eps_by_multiple():
    assert calculate_pe_multiple(eps=5.0, pe_multiple=20.0) == 100.0


def test_calculate_pe_multiple_returns_none_when_eps_is_none():
    assert calculate_pe_multiple(eps=None, pe_multiple=20.0) is None


def test_run_scenario_analysis_returns_bear_base_bull_in_ascending_order():
    output = run_scenario_analysis(
        base_fcf=100.0,
        shares_outstanding=1000.0,
        bear_assumptions=DCFAssumptions(
            growth_rate=0.04, years=5, discount_rate=0.12, terminal_growth_rate=0.02
        ),
        base_assumptions=DCFAssumptions(
            growth_rate=0.08, years=5, discount_rate=0.10, terminal_growth_rate=0.025
        ),
        bull_assumptions=DCFAssumptions(
            growth_rate=0.12, years=5, discount_rate=0.09, terminal_growth_rate=0.03
        ),
        research_run_id=42,
    )

    assert [s.scenario for s in output.scenarios] == ["bear", "base", "bull"]
    bear, base, bull = (s.fair_value_per_share for s in output.scenarios)
    assert bear == pytest.approx(1.1066987713452727)
    assert base == pytest.approx(1.720240228399699)
    assert bull == pytest.approx(2.509103061116436)
    assert bear < base < bull


def test_run_scenario_analysis_attaches_valuation_evidence_per_scenario():
    output = run_scenario_analysis(
        base_fcf=100.0,
        shares_outstanding=1000.0,
        bear_assumptions=DCFAssumptions(
            growth_rate=0.04, years=5, discount_rate=0.12, terminal_growth_rate=0.02
        ),
        base_assumptions=DCFAssumptions(
            growth_rate=0.08, years=5, discount_rate=0.10, terminal_growth_rate=0.025
        ),
        bull_assumptions=DCFAssumptions(
            growth_rate=0.12, years=5, discount_rate=0.09, terminal_growth_rate=0.03
        ),
        research_run_id=42,
    )

    assert len(output.evidence) == 3
    bear_evidence = output.evidence[0]
    assert bear_evidence.research_run_id == 42
    assert bear_evidence.function_name == "run_dcf"
    assert bear_evidence.output_field == "scenarios.bear.fair_value_per_share"
    assert bear_evidence.value == pytest.approx(output.scenarios[0].fair_value_per_share)


def test_run_scenario_analysis_method_and_current_price():
    output = run_scenario_analysis(
        base_fcf=100.0,
        shares_outstanding=1000.0,
        bear_assumptions=DCFAssumptions(
            growth_rate=0.04, years=5, discount_rate=0.12, terminal_growth_rate=0.02
        ),
        base_assumptions=DCFAssumptions(
            growth_rate=0.08, years=5, discount_rate=0.10, terminal_growth_rate=0.025
        ),
        bull_assumptions=DCFAssumptions(
            growth_rate=0.12, years=5, discount_rate=0.09, terminal_growth_rate=0.03
        ),
        research_run_id=42,
        current_price=150.0,
    )

    assert output.method == "dcf_scenario"
    assert output.current_price == 150.0

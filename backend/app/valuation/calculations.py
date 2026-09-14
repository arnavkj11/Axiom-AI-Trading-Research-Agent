"""Deterministic valuation math (CLAUDE.md Rule 1 — Python calculates,
agents only choose or critique assumptions). No LLM/agent code here.
"""

from pydantic import BaseModel, Field

from app.agents.schemas import ScenarioValuation, ValuationOutput, ValuationOutputEvidence


class DCFAssumptions(BaseModel):
    growth_rate: float
    years: int = Field(default=5, gt=0)
    discount_rate: float
    terminal_growth_rate: float


def run_dcf(
    *,
    base_fcf: float,
    shares_outstanding: float,
    assumptions: DCFAssumptions,
    net_cash: float = 0.0,
) -> float:
    """Two-stage DCF: explicit-period growth at growth_rate, then a Gordon-
    growth terminal value at terminal_growth_rate. Returns fair value per
    share.
    """
    if assumptions.terminal_growth_rate >= assumptions.discount_rate:
        raise ValueError("terminal_growth_rate must be less than discount_rate")

    fcf = base_fcf
    pv_fcfs = 0.0
    for year in range(1, assumptions.years + 1):
        fcf *= 1 + assumptions.growth_rate
        pv_fcfs += fcf / (1 + assumptions.discount_rate) ** year

    terminal_value = (
        fcf * (1 + assumptions.terminal_growth_rate)
        / (assumptions.discount_rate - assumptions.terminal_growth_rate)
    )
    pv_terminal_value = terminal_value / (1 + assumptions.discount_rate) ** assumptions.years

    enterprise_value = pv_fcfs + pv_terminal_value
    equity_value = enterprise_value + net_cash
    return equity_value / shares_outstanding


def calculate_pe_multiple(eps: float | None, pe_multiple: float) -> float | None:
    if eps is None:
        return None
    return eps * pe_multiple


def run_scenario_analysis(
    *,
    base_fcf: float,
    shares_outstanding: float,
    bear_assumptions: DCFAssumptions,
    base_assumptions: DCFAssumptions,
    bull_assumptions: DCFAssumptions,
    research_run_id: int,
    net_cash: float = 0.0,
    current_price: float | None = None,
) -> ValuationOutput:
    scenarios: list[ScenarioValuation] = []
    evidence: list[ValuationOutputEvidence] = []
    # A zero/negative price would make upside meaningless (and divide by
    # zero), so treat a bad feed the same as no feed rather than failing
    # the run.
    price = current_price if current_price and current_price > 0 else None

    for label, assumptions in (
        ("bear", bear_assumptions),
        ("base", base_assumptions),
        ("bull", bull_assumptions),
    ):
        fair_value = run_dcf(
            base_fcf=base_fcf,
            shares_outstanding=shares_outstanding,
            assumptions=assumptions,
            net_cash=net_cash,
        )
        upside = upside_pct(fair_value, price)
        scenarios.append(
            ScenarioValuation(
                scenario=label,
                fair_value_per_share=fair_value,
                assumptions=assumptions.model_dump(),
                upside_pct=upside,
            )
        )
        evidence.append(
            ValuationOutputEvidence(
                research_run_id=research_run_id,
                function_name="run_dcf",
                output_field=f"scenarios.{label}.fair_value_per_share",
                value=fair_value,
                assumptions=assumptions.model_dump(),
            )
        )
        if upside is not None:
            # Separate evidence so a claim like "trades 30% below base
            # case" cites the computed comparison, with the price it was
            # measured against travelling alongside it.
            evidence.append(
                ValuationOutputEvidence(
                    research_run_id=research_run_id,
                    function_name="run_scenario_analysis",
                    output_field=f"scenarios.{label}.upside_pct",
                    value=upside,
                    assumptions={**assumptions.model_dump(), "current_price": price},
                )
            )

    return ValuationOutput(
        method="dcf_scenario",
        scenarios=scenarios,
        current_price=current_price,
        evidence=evidence,
        commentary=_commentary(scenarios, price),
    )


def upside_pct(fair_value: float, current_price: float | None) -> float | None:
    """Fractional upside of a fair value over the market price.

    0.30 means the fair value sits 30% above where the stock trades;
    negative means the DCF says it's overvalued. None when there's no
    usable price — the absence of a number is the honest answer, and
    downstream agents are told the price is unknown rather than shown a
    fabricated one.
    """
    if not current_price or current_price <= 0:
        return None
    return (fair_value - current_price) / current_price


def _commentary(scenarios: list[ScenarioValuation], price: float | None) -> str:
    values = (
        f"bear ${scenarios[0].fair_value_per_share:.2f}, "
        f"base ${scenarios[1].fair_value_per_share:.2f}, "
        f"bull ${scenarios[2].fair_value_per_share:.2f}"
    )
    if price is None:
        return f"Two-stage DCF fair value: {values}. No market price available for comparison."
    base_upside = scenarios[1].upside_pct or 0.0
    direction = "above" if base_upside >= 0 else "below"
    return (
        f"Two-stage DCF fair value: {values}. "
        f"At ${price:.2f}, the base case is {abs(base_upside):.1%} {direction} the market price."
    )

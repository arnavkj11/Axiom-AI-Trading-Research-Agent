def gross_margin(revenue: float | None, gross_profit: float | None) -> float | None:
    if not revenue or gross_profit is None:
        return None
    return gross_profit / revenue


def operating_margin(revenue: float | None, operating_income: float | None) -> float | None:
    if not revenue or operating_income is None:
        return None
    return operating_income / revenue


def free_cash_flow(operating_cash_flow: float | None, capex: float | None) -> float | None:
    # Alpha Vantage reports capitalExpenditures as a negative cash outflow,
    # so free cash flow is the sum, not the difference.
    if operating_cash_flow is None or capex is None:
        return None
    return operating_cash_flow + capex


def revenue_growth(current_revenue: float | None, previous_revenue: float | None) -> float | None:
    if not previous_revenue or current_revenue is None:
        return None
    return (current_revenue - previous_revenue) / previous_revenue

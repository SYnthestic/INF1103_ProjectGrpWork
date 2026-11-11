"""SmeCriteria: the statutory SME requirements: at least 30% local
shareholding and annual group revenue of at most S$100 million."""



class SmeCriteria:
    """The statutory SME requirements: at least 30% local shareholding and
    annual group revenue of at most S$100 million. A company above the
    revenue cap is rejected whatever its headcount (`headcount` is accepted
    so callers need not change, but it does not affect the result)."""

    MIN_LOCAL_EQUITY_PCT = 30.0
    MAX_REVENUE_SGD = 100_000_000.0

    def is_sme(
        self, local_equity_pct: float, annual_revenue: float, headcount: int
    ) -> bool:
        return (
            local_equity_pct >= self.MIN_LOCAL_EQUITY_PCT
            and annual_revenue <= self.MAX_REVENUE_SGD
        )

    def fail_reasons(
        self, local_equity_pct: float, annual_revenue: float, headcount: int
    ) -> list[str]:
        """Exactly which SME requirements the company failed."""
        reasons = []
        if local_equity_pct < self.MIN_LOCAL_EQUITY_PCT:
            reasons.append(
                f"Local shareholding is only {local_equity_pct:.1f}%, "
                f"below the required minimum of 30%."
            )
        if annual_revenue > self.MAX_REVENUE_SGD:
            reasons.append(
                f"Annual revenue of S${annual_revenue:,.2f} exceeds the "
                f"S$100,000,000 SME revenue cap."
            )
        return reasons

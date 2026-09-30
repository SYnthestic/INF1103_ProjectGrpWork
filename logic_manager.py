"""
logic_manager.py
================
Procedural business logic engine for:
1. Energy Efficiency Grant (EEG) - Base Tier
2. Energy Efficiency Grant (EEG) - Advanced Tier

Enforces deterministic statutory rules and zero-hallucination math.
Contains NO print() statements and NO file I/O operations.
"""

from typing import Dict, Any, List


def check_sme_status(local_equity_pct: float, annual_rev: float, headcount: int) -> bool:
    """
    Verifies statutory Singapore Enterprise criteria:
    - Minimum 30% local equity held by Citizens or PRs.
    - Annual group turnover <= S$100M OR total group employment <= 200.
    """
    has_local_equity = local_equity_pct >= 30.0
    within_size_caps = (annual_rev <= 100_000_000.0) or (headcount <= 200)
    return has_local_equity and within_size_caps


def calculate_grant_subsidy(cost: float, rate: float, cap: float) -> float:
    """
    Deterministically computes co-funding subsidy in pure Python.
    Prevents any floating point hallucinations.
    """
    return round(min(cost * rate, cap), 2)


def evaluate_eeg_application(user_record: Dict[str, Any], ai_audit: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ingests user input fields alongside AI semantic extractions, applies multi-condition
    statutory rules for EEG Base Tier and Advanced Tier, and produces an audit record
    formatted directly for data_manager.py.
    """
    # 1. Normalize user inputs defensively across both naming conventions
    company_name = user_record.get("Company Name", user_record.get("company_name", "Unknown Entity"))
    industry = user_record.get("Company Industry", user_record.get("industry_sector", "General"))
    revenue = float(user_record.get("Company Total Revenue", user_record.get("annual_revenue_sgd", 0.0)))
    headcount = int(user_record.get("Total Employees", user_record.get("group_employment_size", 0)))
    equity = float(user_record.get("Local Equity", user_record.get("local_shareholding_pct", 0.0)))
    
    # Cost baseline: uses estimated retrofit cost, falling back to baseline annual spend
    retrofit_cost = float(user_record.get(
        "Estimated Retrofit Cost",
        user_record.get("Baseline Energy Expenditure", user_record.get("qualifying_project_cost_sgd", 0.0))
    ))

    # 2. Extract AI semantic attributes
    scope = ai_audit.get("scope_category", "Non-Emissions")
    abatement_pct = float(ai_audit.get("estimated_energy_reduction_pct", 0.0))
    lifetime_tonnes = float(ai_audit.get("estimated_lifetime_abatement_tonnes", 0.0))
    is_preapproved = bool(ai_audit.get("is_preapproved_equipment", False))
    exclusions: List[str] = ai_audit.get("detected_exclusion_keywords", [])
    intervention = ai_audit.get("primary_intervention_type", "Industrial Upgrade")

    # 3. Rule Evaluation & Statutory Gates
    is_sme = check_sme_status(equity, revenue, headcount)
    valid_eeg_scope = scope in ["Scope-1", "Scope-2"]

    # GATE 1: Negative Exclusion Filter (Highest Priority Override)
    if len(exclusions) > 0 or intervention == "Fossil Fuel Modification":
        decision_status = "MANUAL_EXCLUSION_REVIEW"
        matched_scheme = "None (Pending Manual Audit)"
        approved_subsidy = 0.0
        audit_passed = False
        policy_note = (
            f"Disqualifying elements detected: {', '.join(exclusions)}. "
            "Grants strictly exclude second-hand, refurbished, or uncertified machinery."
        )

    # GATE 2: Statutory Non-SME Gate
    elif not is_sme:
        decision_status = "REJECT_NON_SME"
        matched_scheme = "Enterprise Financing Scheme - Green (EFS-Green Loan Facility)"
        approved_subsidy = 0.0
        audit_passed = False
        policy_note = (
            "Applicant exceeds statutory SME thresholds (Requires >=30% local equity "
            "AND <=S$100M revenue or <=200 employees). Referred to debt financing."
        )

    # GATE 3: EEG Advanced Tier Evaluation
    # Criteria: High-impact retrofit, >350t lifetime carbon abatement, Scope 1 or 2
    elif valid_eeg_scope and lifetime_tonnes > 350.0:
        decision_status = "PRE_APPROVED_EEG_ADVANCED"
        matched_scheme = "Energy Efficiency Grant (EEG) - Advanced Tier"
        # 70% co-funding capped at S$350,000 statutory limit
        approved_subsidy = calculate_grant_subsidy(retrofit_cost, 0.70, 350_000.0)
        audit_passed = True
        policy_note = (
            f"Qualifies for EEG Advanced Tier: Confirmed high-impact retrofit with "
            f"{lifetime_tonnes:.1f}t lifetime abatement (>350t threshold). Up to 70% "
            f"co-funding capped at S$350,000.00."
        )

    # GATE 4: EEG Base Tier Evaluation
    # Criteria: Pre-approved machinery (LEDs, HVAC, refrigeration, EVs) or >=20% abatement yield
    elif valid_eeg_scope and (is_preapproved or abatement_pct >= 20.0):
        decision_status = "PRE_APPROVED_EEG_BASE"
        matched_scheme = "Energy Efficiency Grant (EEG) - Base Tier"
        # 70% co-funding capped at S$30,000 statutory ceiling
        approved_subsidy = calculate_grant_subsidy(retrofit_cost, 0.70, 30_000.0)
        audit_passed = True
        policy_note = (
            "Qualifies for EEG Base Tier: Pre-approved energy efficiency equipment upgrade. "
            "Up to 70% co-funding capped at statutory ceiling of S$30,000.00."
        )

    # GATE 5: Low Abatement / Ineligible Scope Rejection
    else:
        decision_status = "REJECT_LOW_IMPACT"
        matched_scheme = "None"
        approved_subsidy = 0.0
        audit_passed = False
        policy_note = (
            f"Application does not meet EEG thresholds. Requires either pre-approved hardware / "
            f">=20% abatement for Base Tier, or >350t lifetime abatement for Advanced Tier."
        )

    # 4. Formatted Record Output for data_manager.py
    return {
        "Company Name": company_name,
        "Company Industry": industry,
        "Company Total Revenue": revenue,
        "Total Employees": headcount,
        "Local Equity": equity,
        "Retrofit Cost": retrofit_cost,
        "GHG Scope": scope,
        "Primary Intervention": intervention,
        "Lifetime Abatement Tonnes": lifetime_tonnes,
        "Is SME": is_sme,
        "Decision Status": decision_status,
        "Matched Scheme": matched_scheme,
        "Approved Subsidy SGD": approved_subsidy,
        "Audit Passed": audit_passed,
        "Policy Explanation": policy_note
    }
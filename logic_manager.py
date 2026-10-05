print('''This is the Logic Manager module. \n 
It is responsible for handling the core logic of the application, \n
 including data processing, calculations, and decision-making based on user inputs and stored data.\n
The Logic Manager interacts with other modules such as the IO Manager for input/output operations, \n
carries out arithmetic and logic operations after the AI Manager has handed over data to it \n
And then pumps down the data to the Data Manager to store and the IO Manager to output
''')

VALID_SCOPES = ["Scope-1", "Scope-2", "Scope-3"]


def check_sme_status(local_equity_pct, annual_revenue, headcount):
    """
    Checks whether the company meets the statutory SME requirements.

    Requirements:
    - At least 30% local shareholding
    - Annual group revenue <= S$100 million OR
      group employment size <= 200 employees

    Returns:
        bool: True if the company qualifies as an SME.
    """

    has_local_equity = local_equity_pct >= 30.0
    within_size_caps = (
        annual_revenue <= 100_000_000.0
        or headcount <= 200
    )

    return has_local_equity and within_size_caps


def get_sme_fail_reasons(local_equity_pct, annual_revenue, headcount):
    """
    Identifies exactly which SME requirements the company failed.

    Returns:
        list: List of reasons for SME ineligibility.
    """

    reasons = []

    if local_equity_pct < 30.0:
        reasons.append(
            f"Local shareholding is only {local_equity_pct:.1f}%, "
            f"below the required minimum of 30%."
        )

    if annual_revenue > 100_000_000.0 and headcount > 200:
        reasons.append(
            f"Both size limits are exceeded: annual revenue is "
            f"S${annual_revenue:,.2f} and group employment is "
            f"{headcount} employees."
        )

    return reasons


def calculate_subsidy(baseline_spend, cofund_percentage, maximum_subsidy):
    """
    Calculates the maximum potential subsidy.

    The calculation is deterministic and does not rely on AI.
    """

    subsidy = baseline_spend * cofund_percentage

    return round(min(subsidy, maximum_subsidy), 2)


def evaluate_grant_application(user_profile, ai_audit):
    """
    Main Logic Layer function.

    Receives:
        user_profile:
            Financial and company information from the input layer.
            Expected keys: annual_revenue_sgd, group_employment_size,
            local_shareholding_pct, proposal_type,
            baseline_annual_energy_expenditure_sgd,
            estimated_retrofit_cost_sgd, reporting_advisory_fee_sgd.

        ai_audit:
            Structured information extracted by ai_manager.py.
            Expected keys: scope_category, estimated_energy_reduction_pct,
            estimated_lifetime_abatement_tonnes,
            detected_exclusion_keywords, primary_intervention_type.

    Returns:
        dict containing:
            - SME eligibility
            - decision status
            - reasons
            - recommendations
            - matched grants
            - potential subsidy
            - audit status

    Priority order (highest first):
        1. Exclusion keywords / fossil-fuel modification -> manual review
        2. Non-SME -> statutory rejection
        3. ESG Reporting / Advisory proposals -> SRG (self-declared by
           applicant, doesn't depend on GHG scope classification)
        4. Unclassifiable GHG scope on an equipment proposal -> manual review
        5. EEG-Advanced Tier (lifetime abatement > 350 tonnes)
        6. EEG-Base Tier (Scope-1, abatement >= 20%)
        7. ESP (Scope-2/3, abatement >= 10%)
        8. Reject - low impact
    """

    # ---------------------------------------------------------
    # 1. Extract company information
    # ---------------------------------------------------------

    annual_revenue = user_profile.get(
        "annual_revenue_sgd", 0.0
    )

    headcount = user_profile.get(
        "group_employment_size", 0
    )

    local_equity = user_profile.get(
        "local_shareholding_pct", 0.0
    )

    baseline_spend = user_profile.get(
        "baseline_annual_energy_expenditure_sgd", 0.0
    )

    # Applicant self-declares proposal type in io_manager.py, so this is
    # taken directly from user_profile rather than inferred by the AI.
    proposal_type = user_profile.get(
        "proposal_type", "Equipment / Energy Upgrade"
    )

    reporting_advisory_fee = user_profile.get(
        "reporting_advisory_fee_sgd", 0.0
    )

    # ---------------------------------------------------------
    # 2. Extract AI information
    # ---------------------------------------------------------

    scope = ai_audit.get(
        "scope_category", "Unknown"
    )

    abatement = ai_audit.get(
        "estimated_energy_reduction_pct", 0.0
    )

    exclusions = ai_audit.get(
        "detected_exclusion_keywords", []
    )

    intervention = ai_audit.get(
        "primary_intervention_type", ""
    )

    lifetime_abatement_tonnes = ai_audit.get(
        "estimated_lifetime_abatement_tonnes", 0.0
    )

    # ---------------------------------------------------------
    # 3. Initialise output
    # ---------------------------------------------------------

    reasons = []
    recommendations = []
    matched_schemes = []

    approved_subsidy = 0.0

    decision_status = "MANUAL_REVIEW"

    # ---------------------------------------------------------
    # 4. Check SME eligibility
    # ---------------------------------------------------------

    is_sme = check_sme_status(
        local_equity,
        annual_revenue,
        headcount
    )

    sme_fail_reasons = get_sme_fail_reasons(
        local_equity,
        annual_revenue,
        headcount
    )

    # ---------------------------------------------------------
    # 5. Check exclusion rules FIRST
    # ---------------------------------------------------------

    # Exclusions take priority over normal grant approval.
    if len(exclusions) > 0:

        decision_status = "MANUAL_EXCLUSION_REVIEW"

        reasons.append(
            "Potentially prohibited equipment or modification "
            "was detected in the proposal."
        )

        for exclusion in exclusions:
            reasons.append(
                f"Detected exclusion: {exclusion}"
            )

        recommendations.append(
            "Remove the potentially prohibited equipment or "
            "modification from the proposal."
        )

        recommendations.append(
            "Obtain a quotation for compliant, brand-new equipment "
            "where applicable."
        )

        recommendations.append(
            "Resubmit the revised proposal for eligibility assessment."
        )

        matched_schemes = [
            "Enterprise Sustainability Programme "
            "(Subject to re-quotation)"
        ]

    # ---------------------------------------------------------
    # 6. Check fossil fuel modification
    # ---------------------------------------------------------

    elif intervention == "Fossil Fuel Modification":

        decision_status = "MANUAL_EXCLUSION_REVIEW"

        reasons.append(
            "The proposed intervention involves fossil-fuel "
            "modification, which may fall under a grant exclusion."
        )

        recommendations.append(
            "Consider replacing the fossil-fuel modification with "
            "an energy-efficiency or low-carbon alternative."
        )

        recommendations.append(
            "Submit supporting technical documentation for "
            "manual eligibility review."
        )

    # ---------------------------------------------------------
    # 7. Check SME eligibility (statutory rejection takes priority
    #    over every approval / advisory path below, including SRG)
    # ---------------------------------------------------------

    elif not is_sme:

        decision_status = "REJECT_NON_SME"

        reasons.extend(sme_fail_reasons)

        recommendations.append(
            "Review the company's local shareholding structure "
            "and SME size criteria."
        )

        if local_equity < 30.0:
            recommendations.append(
                "Increase local shareholding to at least 30% "
                "if commercially and legally appropriate."
            )

        if annual_revenue > 100_000_000.0 and headcount > 200:
            recommendations.append(
                "The company exceeds both SME size limits. "
                "SME-targeted co-funding is therefore unavailable "
                "under these criteria."
            )

        recommendations.append(
            "Consider the Enterprise Financing Scheme – Green "
            "(EFS-Green) as an alternative financing route."
        )

        matched_schemes = [
            "Enterprise Financing Scheme – Green (EFS-Green)"
        ]

    # ---------------------------------------------------------
    # 8. Sustainability Reporting Grant
    # ---------------------------------------------------------
    # Checked before the GHG-scope validity check below, since a
    # reporting/advisory proposal has no GHG scope to classify — it is
    # a different proposal category entirely, self-declared by the
    # applicant in io_manager.py rather than inferred by the AI.

    elif proposal_type == "ESG Reporting / Advisory":

        decision_status = "PRE_APPROVED_SRG"

        approved_subsidy = calculate_subsidy(
            reporting_advisory_fee,
            0.30,
            150_000.0
        )

        matched_schemes = [
            "Sustainability Reporting Grant (SRG)"
        ]

        reasons.append(
            "Company meets the SME eligibility requirements."
        )

        reasons.append(
            "Proposal covers an inaugural ESG assurance report "
            "rather than an equipment or capability upgrade."
        )

        recommendations.append(
            "Ensure the external assurance statement covers, at "
            "minimum, Scope 1 and Scope 2 emissions in line with "
            "ISSB and GRI standards."
        )

    # ---------------------------------------------------------
    # 9. Check that the AI could classify a GHG scope at all
    # ---------------------------------------------------------
    # Only equipment/energy-upgrade proposals reach this point, since
    # reporting proposals were already routed to SRG above.

    elif scope not in VALID_SCOPES:

        decision_status = "MANUAL_REVIEW"

        reasons.append(
            f"GHG Protocol scope could not be determined "
            f"(AI returned '{scope}')."
        )

        recommendations.append(
            "Provide a clearer description of the intervention so "
            "the AI Manager can classify it under Scope 1, 2, or 3."
        )

    # ---------------------------------------------------------
    # 10. Energy Efficiency Grant - Advanced Tier
    # ---------------------------------------------------------
    # Requires >350 tonnes of independently-verified lifetime carbon
    # abatement. Checked before the Base Tier since it supersedes it
    # when the higher threshold is met.

    elif lifetime_abatement_tonnes > 350.0:

        decision_status = "PRE_APPROVED_TIER_1_ADVANCED"

        approved_subsidy = calculate_subsidy(
            baseline_spend,
            0.70,
            350_000.0
        )

        matched_schemes = [
            "Energy Efficiency Grant (EEG) - Advanced Tier"
        ]

        reasons.append(
            "Company meets the SME eligibility requirements."
        )

        reasons.append(
            f"Estimated lifetime carbon abatement of "
            f"{lifetime_abatement_tonnes:.1f} tonnes exceeds the "
            "350-tonne Advanced Tier threshold."
        )

        recommendations.append(
            "Engage an independent energy assessor to verify the "
            "lifetime abatement estimate before final disbursement."
        )

    # ---------------------------------------------------------
    # 11. Energy Efficiency Grant - Base Tier
    # ---------------------------------------------------------

    elif scope == "Scope-1" and abatement >= 20.0:

        decision_status = "PRE_APPROVED_TIER_1"

        approved_subsidy = calculate_subsidy(
            baseline_spend,
            0.70,
            30_000.0
        )

        matched_schemes = [
            "Energy Efficiency Grant (EEG) - Base Tier",
            "Enterprise Sustainability Programme (ESP)"
        ]

        reasons.append(
            "Company meets the SME eligibility requirements."
        )

        reasons.append(
            "Proposal targets Scope-1 emissions."
        )

        reasons.append(
            f"Estimated energy reduction of {abatement:.1f}% "
            "meets the 20% threshold for this system's "
            "fast-track rule."
        )

    # ---------------------------------------------------------
    # 12. Enterprise Sustainability Programme
    # ---------------------------------------------------------

    elif scope in ["Scope-2", "Scope-3"] and abatement >= 10.0:

        decision_status = "PROVISIONAL_APPROVAL_TIER_2"

        approved_subsidy = calculate_subsidy(
            baseline_spend,
            0.50,
            20_000.0
        )

        matched_schemes = [
            "Enterprise Sustainability Programme (ESP)"
        ]

        reasons.append(
            "Company meets the SME eligibility requirements."
        )

        reasons.append(
            f"Proposal targets {scope} emissions."
        )

        reasons.append(
            f"Estimated energy reduction of {abatement:.1f}% "
            "meets the minimum threshold for this system's "
            "capability-support rule."
        )

        recommendations.append(
            "Prepare supporting baseline energy and emissions "
            "documentation for final assessment."
        )

    # ---------------------------------------------------------
    # 13. Low-impact proposal
    # ---------------------------------------------------------

    else:

        decision_status = "REJECT_LOW_IMPACT"

        reasons.append(
            f"Estimated energy reduction of {abatement:.1f}% "
            "is below the minimum threshold of 10.0% used "
            "by this system."
        )

        recommendations.append(
            "Consider increasing the projected energy-efficiency "
            "improvement to at least 10%."
        )

        recommendations.append(
            "Consider additional energy-efficiency measures such "
            "as equipment upgrades, HVAC optimisation, lighting "
            "efficiency, or other applicable interventions."
        )

        recommendations.append(
            "Recalculate the expected energy reduction after "
            "modifying the proposed project."
        )

    # ---------------------------------------------------------
    # 14. Determine whether audit passed
    # ---------------------------------------------------------

    audit_passed = decision_status in [
        "PRE_APPROVED_TIER_1",
        "PRE_APPROVED_TIER_1_ADVANCED",
        "PROVISIONAL_APPROVAL_TIER_2",
        "PRE_APPROVED_SRG"
    ]

    # ---------------------------------------------------------
    # 15. Return structured result
    # ---------------------------------------------------------

    return {
        "is_sme": is_sme,
        "decision_status": decision_status,

        "reasons": reasons,

        "recommendations": recommendations,

        "matched_schemes": matched_schemes,

        "approved_subsidy_sgd": approved_subsidy,

        "audit_passed": audit_passed
    }
import hashlib
import hmac
import math
import secrets


def module_description():
    return (
        "This is the Logic Manager module.\n"
        "It is responsible for handling the core logic of the application, "
        "including data processing, calculations, and decision-making based "
        "on user inputs and stored data.\n"
        "The Logic Manager interacts with other modules such as the IO Manager "
        "for input/output operations, carries out arithmetic and logic "
        "operations after the AI Manager has handed over data to it, "
        "and then passes the data on to the Data Manager to store and the "
        "IO Manager to output."
    )


VALID_SCOPES = ["Scope-1", "Scope-2", "Scope-3"]

# Energy-reduction thresholds (percent), as in the project's rule set:
#   >= 20  Scope-1 fast-track (EEG Base Tier)
#   >= 15  provisional approval for any scope (ESP, 50% co-funding)
#   >= 10  below 15 but at least 10: referred to a person for review
#   <  10  rejected as insufficient decarbonisation yield
FAST_TRACK_MIN_PCT = 20.0
PROVISIONAL_MIN_PCT = 15.0
MINIMUM_IMPACT_PCT = 10.0

# Decisions whose subsidy comes from the baseline energy spend (the
# reporting grant is based on the advisory fee instead).
EQUIPMENT_SUBSIDY_STATUSES = (
    "PRE_APPROVED_TIER_1",
    "PRE_APPROVED_TIER_1_ADVANCED",
    "PROVISIONAL_APPROVAL_TIER_2",
)


def _number(value, default=0.0):
    """A finite float, or `default` for None, text, NaN or infinity.
    Keeps one bad value from crashing the whole evaluation."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    return value if math.isfinite(value) else default


_PLACEHOLDER_KEYWORDS = {
    "none", "no", "nil", "null", "n/a", "na", "-", "--", "not applicable",
    "none detected", "no exclusions", "no exclusion", "no keywords",
    "none found", "nothing", "unknown",
}


def _string_list(value):
    """The exclusion keywords as a list of strings (a lone string is kept
    whole instead of being read letter by letter). Placeholders such as
    "none" or "N/A" are not exclusions and are dropped."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    items = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        lowered = text.lower().strip(".")
        if text and lowered not in _PLACEHOLDER_KEYWORDS and not lowered.startswith("none "):
            items.append(text)
    return items


# =========================================================
# Password hashing (SHA-256)
# =========================================================
# Passwords are never stored. Instead we store:
#   - a random 16-byte salt, unique per user, so two users with the
#     same password get different hashes (defeats rainbow tables)
#   - the SHA-256 based PBKDF2 hash of salt + password, repeated
#     HASH_ITERATIONS times so brute-forcing is slow
# Comparison uses hmac.compare_digest (constant time) so attackers
# can't learn the hash byte-by-byte from response timing.
HASH_ALGORITHM = "pbkdf2_sha256"
HASH_ITERATIONS = 200_000
SALT_BYTES = 16


def hash_password(password, salt_hex=None, iterations=HASH_ITERATIONS):
    """
    Hashes a password with SHA-256 (PBKDF2-HMAC-SHA256).

    If salt_hex is None a fresh random salt is generated (new account);
    otherwise the stored salt is reused (login check).

    Returns:
        dict: algorithm, iterations, salt (hex), password_hash (hex)
    """

    if salt_hex is None:
        salt_hex = secrets.token_hex(SALT_BYTES)

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations
    )

    return {
        "algorithm": HASH_ALGORITHM,
        "iterations": iterations,
        "salt": salt_hex,
        "password_hash": digest.hex()
    }


def build_new_user_record(username, password):
    """Builds the record the Data Manager stores for a new account."""

    record = {"username": username}
    record.update(hash_password(password))
    return record


# Upper limits used when checking a login, so a hand-edited or damaged
# users.json (or an absurdly long password) cannot hang or crash the app.
MAX_PASSWORD_CHARS_CHECKED = 256
MAX_STORED_ITERATIONS = 5_000_000


def verify_password(password, user_record):
    """
    Checks a login attempt against a stored user record.

    user_record may be None (unknown username). We still run a hash in
    that case so a wrong username takes as long as a wrong password,
    which stops attackers discovering which usernames exist.

    A damaged record (missing/non-hex salt, bad iteration count, wrong
    types) simply fails the login instead of crashing the program.

    Returns:
        bool: True if the password is correct.
    """

    if not isinstance(password, str) or len(password) > MAX_PASSWORD_CHARS_CHECKED:
        return False

    if not isinstance(user_record, dict):
        hash_password(password)  # dummy work to equalise timing
        return False

    salt = user_record.get("salt")
    stored_hash = user_record.get("password_hash")
    iterations = user_record.get("iterations", HASH_ITERATIONS)

    if (
        not isinstance(salt, str)
        or not isinstance(stored_hash, str)
        or isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or not 0 < iterations <= MAX_STORED_ITERATIONS
    ):
        return False

    try:
        attempt = hash_password(password, salt_hex=salt, iterations=iterations)
        return hmac.compare_digest(
            attempt["password_hash"].encode("ascii"),
            stored_hash.encode("ascii")
        )
    except (ValueError, TypeError, UnicodeError):
        return False


SME_MIN_LOCAL_EQUITY_PCT = 30.0
SME_MAX_REVENUE_SGD = 100_000_000.0


# Menu text chosen by the applicant -> the scheme name the rules produce.
# Other choices (e.g. Enterprise Development Grant, "Others") have no
# matching rule, so they are never flagged.
CHOSEN_SCHEME_KEYWORDS = (
    ("advanced tier", "Energy Efficiency Grant (EEG) - Advanced Tier"),
    ("base tier", "Energy Efficiency Grant (EEG) - Base Tier"),
    ("reporting", "Sustainability Reporting Grant (SRG)"),
)


def scheme_mismatch_note(chosen_scheme, matched_schemes):
    """Returns a recommendation when the scheme the applicant picked is not
    the one the rules matched, otherwise None. Informational only: the
    decision itself is never changed by the applicant's choice."""

    if not isinstance(chosen_scheme, str) or not matched_schemes:
        return None

    lowered = chosen_scheme.lower()
    for keyword, expected_scheme in CHOSEN_SCHEME_KEYWORDS:
        if keyword in lowered:
            if expected_scheme in matched_schemes:
                return None
            chosen_name = chosen_scheme.lstrip("0123456789. ").strip()
            return (
                f"You selected '{chosen_name}', but this proposal matched: "
                f"{'; '.join(matched_schemes)}. Check that you are applying "
                "for the right scheme."
            )
    return None


def check_sme_status(local_equity_pct, annual_revenue, headcount):
    """
    Checks whether the company meets the statutory SME requirements.

    Requirements:
    - At least 30% local shareholding
    - Annual group revenue of at most S$100 million (a company above the
      revenue cap is rejected whatever its headcount; `headcount` is kept
      as a parameter for callers but no longer affects the result)

    Returns:
        bool: True if the company qualifies as an SME.
    """

    has_local_equity = local_equity_pct >= SME_MIN_LOCAL_EQUITY_PCT
    within_revenue_cap = annual_revenue <= SME_MAX_REVENUE_SGD

    return has_local_equity and within_revenue_cap


def get_sme_fail_reasons(local_equity_pct, annual_revenue, headcount):
    """
    Identifies exactly which SME requirements the company failed.

    Returns:
        list: List of reasons for SME ineligibility.
    """

    reasons = []

    if local_equity_pct < SME_MIN_LOCAL_EQUITY_PCT:
        reasons.append(
            f"Local shareholding is only {local_equity_pct:.1f}%, "
            f"below the required minimum of 30%."
        )

    if annual_revenue > SME_MAX_REVENUE_SGD:
        reasons.append(
            f"Annual revenue of S${annual_revenue:,.2f} exceeds the "
            f"S$100,000,000 SME revenue cap."
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
        5. EEG-Advanced Tier (lifetime abatement > 350 tonnes and
           energy reduction >= 10%)
        6. EEG-Base Tier (Scope-1, energy reduction >= 20%)
        7. ESP provisional approval (any scope, energy reduction >= 15%)
        8. Manual review (energy reduction 10% to under 15%)
        9. Reject - low impact (energy reduction under 10%)
    """

    # ---------------------------------------------------------
    # 1. Extract company information
    # ---------------------------------------------------------

    annual_revenue = _number(user_profile.get("annual_revenue_sgd"))

    headcount = int(_number(user_profile.get("group_employment_size")))

    local_equity = _number(user_profile.get("local_shareholding_pct"))

    baseline_spend = _number(
        user_profile.get("baseline_annual_energy_expenditure_sgd")
    )

    # Applicant self-declares proposal type in io_manager.py, so this is
    # taken directly from user_profile rather than inferred by the AI.
    proposal_type = user_profile.get(
        "proposal_type", "Equipment / Energy Upgrade"
    )

    sustainability_grant = user_profile.get(
        "sustainability_grant", 0
    )

    reporting_advisory_fee = _number(
        user_profile.get("reporting_advisory_fee_sgd")
    )

    retrofit_cost = _number(
        user_profile.get("estimated_retrofit_cost_sgd")
    )

    # ---------------------------------------------------------
    # 2. Extract AI information
    # ---------------------------------------------------------

    scope = ai_audit.get(
        "scope_category", "Unknown"
    )

    abatement = _number(
        ai_audit.get("estimated_energy_reduction_pct")
    )

    exclusions = _string_list(
        ai_audit.get("detected_exclusion_keywords")
    )

    intervention = ai_audit.get(
        "primary_intervention_type", ""
    )

    lifetime_abatement_tonnes = _number(
        ai_audit.get("estimated_lifetime_abatement_tonnes")
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

        if annual_revenue > SME_MAX_REVENUE_SGD:
            recommendations.append(
                "The company's revenue exceeds the SME cap of S$100 million. "
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

    elif proposal_type == "ESG Reporting / Advisory" and reporting_advisory_fee <= 0:

        # The grant is a percentage of the fee, so without a fee there is
        # nothing to approve (it would be a "pre-approval" for SGD 0).
        decision_status = "MANUAL_REVIEW"

        reasons.append(
            "No valid external ESG reporting/advisory fee was provided, "
            "so a subsidy cannot be calculated."
        )

        recommendations.append(
            "Provide the quoted reporting/advisory fee (more than SGD 0) "
            "and resubmit the proposal."
        )

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
    # 8b. Equipment proposals need a positive baseline energy spend
    # ---------------------------------------------------------
    # The subsidy is calculated from the baseline spend, so a zero or
    # missing value would otherwise "pre-approve" a SGD 0 subsidy.

    elif baseline_spend <= 0:

        decision_status = "MANUAL_REVIEW"

        reasons.append(
            "No valid baseline annual energy expenditure was provided, "
            "so a subsidy cannot be calculated."
        )

        recommendations.append(
            "Provide the company's baseline annual energy expenditure "
            "(more than SGD 0) and resubmit the proposal."
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
    # when the higher threshold is met. The AI's tonnes figure is only an
    # estimate, so the proposal must also reach the minimum energy
    # reduction (a claimed 400 tonnes with 0% reduction does not qualify).

    elif lifetime_abatement_tonnes > 350.0 and abatement >= MINIMUM_IMPACT_PCT:

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

    elif scope == "Scope-1" and abatement >= FAST_TRACK_MIN_PCT:

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
    # Any valid scope that misses the Scope-1 fast track but still reaches
    # 15% (so Scope-1 at 15-20% lands here too).

    elif abatement >= PROVISIONAL_MIN_PCT:

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
            "meets the 15% threshold for provisional "
            "capability-support approval."
        )

        recommendations.append(
            "Prepare supporting baseline energy and emissions "
            "documentation for final assessment."
        )

    # ---------------------------------------------------------
    # 13. Borderline impact: 10% to under 15%
    # ---------------------------------------------------------
    # Above the rejection line but below the provisional-approval line, so
    # neither an automatic approval nor an automatic rejection is fair.

    elif abatement >= MINIMUM_IMPACT_PCT:

        decision_status = "MANUAL_REVIEW"

        reasons.append(
            f"Estimated energy reduction of {abatement:.1f}% meets the "
            f"minimum of {MINIMUM_IMPACT_PCT:.0f}% but is below the "
            f"{PROVISIONAL_MIN_PCT:.0f}% needed for provisional approval."
        )

        recommendations.append(
            "Submit supporting baseline and measurement data so a "
            "reviewer can assess the proposal."
        )

        recommendations.append(
            "Consider measures that raise the projected energy reduction "
            f"to at least {PROVISIONAL_MIN_PCT:.0f}%."
        )

    # ---------------------------------------------------------
    # 14. Low-impact proposal
    # ---------------------------------------------------------

    else:

        decision_status = "REJECT_LOW_IMPACT"

        reasons.append(
            f"Estimated energy reduction of {abatement:.1f}% "
            f"is below the minimum threshold of {MINIMUM_IMPACT_PCT:.1f}% "
            "used by this system."
        )

        recommendations.append(
            "Consider increasing the projected energy-efficiency "
            "improvement to at least 15%."
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
    # 14b. Never subsidise more than the project costs
    # ---------------------------------------------------------
    # Equipment subsidies are worked out from the baseline energy spend, so
    # a small retrofit could otherwise be "granted" more than it costs.
    # (A missing cost of 0 means "not stated" and applies no cap.)

    if (
        decision_status in EQUIPMENT_SUBSIDY_STATUSES
        and 0 < retrofit_cost < approved_subsidy
    ):
        approved_subsidy = round(retrofit_cost, 2)
        reasons.append(
            f"Subsidy limited to the stated retrofit cost of "
            f"SGD {retrofit_cost:,.2f}."
        )

    # ---------------------------------------------------------
    # 14c. Tell the applicant if they picked a different scheme
    # ---------------------------------------------------------

    if decision_status in EQUIPMENT_SUBSIDY_STATUSES + ("PRE_APPROVED_SRG",):
        mismatch_note = scheme_mismatch_note(sustainability_grant, matched_schemes)
        if mismatch_note:
            recommendations.append(mismatch_note)

    # ---------------------------------------------------------
    # 15. Determine whether audit passed
    # ---------------------------------------------------------

    audit_passed = decision_status in [
        "PRE_APPROVED_TIER_1",
        "PRE_APPROVED_TIER_1_ADVANCED",
        "PROVISIONAL_APPROVAL_TIER_2",
        "PRE_APPROVED_SRG"
    ]

    # ---------------------------------------------------------
    # 16. Return structured result
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
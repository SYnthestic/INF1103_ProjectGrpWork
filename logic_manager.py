import hashlib
import hmac
import math
import secrets
from typing import Any

Case = dict[str, Any]  # numbers and labels the rules look at
Decision = dict[str, Any]  # what one rule returns


def module_description() -> str:
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


def _number(value: Any, default: float = 0.0) -> float:
    """A finite float, or `default` for None, text, NaN or infinity.
    Keeps one bad value from crashing the whole evaluation."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    return value if math.isfinite(value) else default


_PLACEHOLDER_KEYWORDS = {
    "none",
    "no",
    "nil",
    "null",
    "n/a",
    "na",
    "-",
    "--",
    "not applicable",
    "none detected",
    "no exclusions",
    "no exclusion",
    "no keywords",
    "none found",
    "nothing",
    "unknown",
}


def _string_list(value: Any) -> list[str]:
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
        if (
            text
            and lowered not in _PLACEHOLDER_KEYWORDS
            and not lowered.startswith("none ")
        ):
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


def hash_password(
    password: str, salt_hex: str | None = None, iterations: int = HASH_ITERATIONS
) -> dict[str, Any]:
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
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
    )

    return {
        "algorithm": HASH_ALGORITHM,
        "iterations": iterations,
        "salt": salt_hex,
        "password_hash": digest.hex(),
    }


def build_new_user_record(username: str, password: str) -> dict[str, Any]:
    """Builds the record the Data Manager stores for a new account."""

    record = {"username": username}
    record.update(hash_password(password))
    return record


# Upper limits used when checking a login, so a hand-edited or damaged
# users.json (or an absurdly long password) cannot hang or crash the app.
MAX_PASSWORD_CHARS_CHECKED = 256
MAX_STORED_ITERATIONS = 5_000_000


def verify_password(password: Any, user_record: Any) -> bool:
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
            attempt["password_hash"].encode("ascii"), stored_hash.encode("ascii")
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


def scheme_mismatch_note(chosen_scheme: Any, matched_schemes: list[str]) -> str | None:
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


def check_sme_status(
    local_equity_pct: float, annual_revenue: float, headcount: int
) -> bool:
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


def get_sme_fail_reasons(
    local_equity_pct: float, annual_revenue: float, headcount: int
) -> list[str]:
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


def calculate_subsidy(
    baseline_spend: float, cofund_percentage: float, maximum_subsidy: float
) -> float:
    """
    Calculates the maximum potential subsidy.

    The calculation is deterministic and does not rely on AI.
    """

    subsidy = baseline_spend * cofund_percentage

    return round(min(subsidy, maximum_subsidy), 2)


# =========================================================
# Grant decision engine
# =========================================================
# The decision is a list of small rules (see DECISION_RULES at the bottom).
# Each rule looks at one "case" (the applicant's numbers plus the cleaned AI
# audit) and either returns a decision or returns None to say "not mine".
# The first rule that returns a decision wins, so the ORDER of that list is
# the priority order of the grant rules.

EEG_ADVANCED_MIN_TONNES = 350.0

# Co-funding rate and maximum subsidy (SGD) of each scheme.
EEG_ADVANCED_FUNDING = (0.70, 350_000.0)
EEG_BASE_FUNDING = (0.70, 30_000.0)
ESP_FUNDING = (0.50, 20_000.0)
SRG_FUNDING = (0.30, 150_000.0)

EEG_ADVANCED_NAME = "Energy Efficiency Grant (EEG) - Advanced Tier"
EEG_BASE_NAME = "Energy Efficiency Grant (EEG) - Base Tier"
ESP_NAME = "Enterprise Sustainability Programme (ESP)"
SRG_NAME = "Sustainability Reporting Grant (SRG)"
EFS_GREEN_NAME = "Enterprise Financing Scheme – Green (EFS-Green)"

REPORTING_PROPOSAL = "ESG Reporting / Advisory"
FOSSIL_FUEL_LABEL = "Fossil Fuel Modification"

PASSING_STATUSES = (
    "PRE_APPROVED_TIER_1",
    "PRE_APPROVED_TIER_1_ADVANCED",
    "PROVISIONAL_APPROVAL_TIER_2",
    "PRE_APPROVED_SRG",
)


def _decision(
    status: str,
    reasons: list[str] | None = None,
    recommendations: list[str] | None = None,
    matched_schemes: list[str] | None = None,
    subsidy: float = 0.0,
) -> Decision:
    """What a rule returns: the outcome plus everything the report shows."""
    return {
        "decision_status": status,
        "reasons": list(reasons or []),
        "recommendations": list(recommendations or []),
        "matched_schemes": list(matched_schemes or []),
        "approved_subsidy_sgd": subsidy,
    }


def build_case(user_profile: dict[str, Any], ai_audit: dict[str, Any]) -> Case:
    """Pulls the numbers and labels the rules need out of the applicant's
    profile and the AI audit, replacing anything missing or malformed with
    a safe default so no rule has to check types itself."""

    annual_revenue = _number(user_profile.get("annual_revenue_sgd"))
    headcount = int(_number(user_profile.get("group_employment_size")))
    local_equity = _number(user_profile.get("local_shareholding_pct"))

    return {
        # Company
        "annual_revenue": annual_revenue,
        "headcount": headcount,
        "local_equity": local_equity,
        "is_sme": check_sme_status(local_equity, annual_revenue, headcount),
        "sme_fail_reasons": get_sme_fail_reasons(
            local_equity, annual_revenue, headcount
        ),
        # Proposal (self-declared by the applicant in io_manager.py, so it
        # is taken from the profile rather than inferred by the AI)
        "proposal_type": user_profile.get(
            "proposal_type", "Equipment / Energy Upgrade"
        ),
        "chosen_scheme": user_profile.get("sustainability_grant", 0),
        "baseline_spend": _number(
            user_profile.get("baseline_annual_energy_expenditure_sgd")
        ),
        "retrofit_cost": _number(user_profile.get("estimated_retrofit_cost_sgd")),
        "advisory_fee": _number(user_profile.get("reporting_advisory_fee_sgd")),
        # AI audit
        "scope": ai_audit.get("scope_category", "Unknown"),
        "energy_reduction_pct": _number(ai_audit.get("estimated_energy_reduction_pct")),
        "lifetime_tonnes": _number(ai_audit.get("estimated_lifetime_abatement_tonnes")),
        "exclusions": _string_list(ai_audit.get("detected_exclusion_keywords")),
        "intervention": ai_audit.get("primary_intervention_type", ""),
        "ai_failed": str(ai_audit.get("ai_status", "ok")).strip().lower() == "failed",
    }


def rule_ai_failed(case):
    """The AI could not analyse the narrative, so no approval is safe."""
    if not case["ai_failed"]:
        return None
    return _decision(
        "MANUAL_REVIEW",
        reasons=[
            "The AI analysis failed, so the proposal could not be assessed automatically."
        ],
        recommendations=[
            "Run the analysis again, or send the proposal for manual review."
        ],
    )


# ---------------------------------------------------------
# Rules, in priority order (each returns a decision or None)
# ---------------------------------------------------------


def rule_exclusion_keywords(case: Case) -> Decision | None:
    """1. Prohibited equipment named by the AI -> exclusion review."""
    if not case["exclusions"]:
        return None

    reasons = [
        "Potentially prohibited equipment or modification was detected in the proposal."
    ]
    reasons += [f"Detected exclusion: {exclusion}" for exclusion in case["exclusions"]]

    return _decision(
        "MANUAL_EXCLUSION_REVIEW",
        reasons,
        [
            "Remove the potentially prohibited equipment or modification from the proposal.",
            "Obtain a quotation for compliant, brand-new equipment where applicable.",
            "Resubmit the revised proposal for eligibility assessment.",
        ],
        ["Enterprise Sustainability Programme (Subject to re-quotation)"],
    )


def rule_fossil_fuel_modification(case: Case) -> Decision | None:
    """2. Fossil-fuel modification may be an excluded activity."""
    if case["intervention"] != FOSSIL_FUEL_LABEL:
        return None

    return _decision(
        "MANUAL_EXCLUSION_REVIEW",
        [
            "The proposed intervention involves fossil-fuel modification, "
            "which may fall under a grant exclusion."
        ],
        [
            "Consider replacing the fossil-fuel modification with an "
            "energy-efficiency or low-carbon alternative.",
            "Submit supporting technical documentation for manual eligibility review.",
        ],
    )


def rule_not_an_sme(case: Case) -> Decision | None:
    """3. Statutory SME check. Rejection here outranks every approval
    path below, including the reporting grant."""
    if case["is_sme"]:
        return None

    recommendations = [
        "Review the company's local shareholding structure and SME size criteria."
    ]
    if case["local_equity"] < SME_MIN_LOCAL_EQUITY_PCT:
        recommendations.append(
            "Increase local shareholding to at least 30% "
            "if commercially and legally appropriate."
        )
    if case["annual_revenue"] > SME_MAX_REVENUE_SGD:
        recommendations.append(
            "The company's revenue exceeds the SME cap of S$100 million. "
            "SME-targeted co-funding is therefore unavailable "
            "under these criteria."
        )
    recommendations.append(
        "Consider the Enterprise Financing Scheme – Green "
        "(EFS-Green) as an alternative financing route."
    )

    return _decision(
        "REJECT_NON_SME", case["sme_fail_reasons"], recommendations, [EFS_GREEN_NAME]
    )


# A reporting/advisory proposal has no GHG scope to classify, so the two
# reporting rules run before the scope check further down.


def rule_reporting_without_fee(case: Case) -> Decision | None:
    """4a. The grant is a percentage of the fee, so no fee = nothing to approve."""
    if case["proposal_type"] != REPORTING_PROPOSAL or case["advisory_fee"] > 0:
        return None

    return _decision(
        "MANUAL_REVIEW",
        [
            "No valid external ESG reporting/advisory fee was provided, "
            "so a subsidy cannot be calculated."
        ],
        [
            "Provide the quoted reporting/advisory fee (more than SGD 0) "
            "and resubmit the proposal."
        ],
    )


def rule_reporting_grant(case: Case) -> Decision | None:
    """4b. Sustainability Reporting Grant (30% of the fee, capped)."""
    if case["proposal_type"] != REPORTING_PROPOSAL:
        return None

    return _decision(
        "PRE_APPROVED_SRG",
        [
            "Company meets the SME eligibility requirements.",
            "Proposal covers an inaugural ESG assurance report "
            "rather than an equipment or capability upgrade.",
        ],
        [
            "Ensure the external assurance statement covers, at "
            "minimum, Scope 1 and Scope 2 emissions in line with "
            "ISSB and GRI standards."
        ],
        [SRG_NAME],
        calculate_subsidy(case["advisory_fee"], *SRG_FUNDING),
    )


def rule_missing_baseline_spend(case: Case) -> Decision | None:
    """5. Equipment subsidies come from the baseline energy spend, so a zero
    or missing value would otherwise pre-approve a SGD 0 subsidy."""
    if case["baseline_spend"] > 0:
        return None

    return _decision(
        "MANUAL_REVIEW",
        [
            "No valid baseline annual energy expenditure was provided, "
            "so a subsidy cannot be calculated."
        ],
        [
            "Provide the company's baseline annual energy expenditure "
            "(more than SGD 0) and resubmit the proposal."
        ],
    )


def rule_unclassified_scope(case: Case) -> Decision | None:
    """6. The AI could not place an equipment proposal in Scope 1, 2 or 3."""
    if case["scope"] in VALID_SCOPES:
        return None

    return _decision(
        "MANUAL_REVIEW",
        [
            f"GHG Protocol scope could not be determined (AI returned '{case['scope']}')."
        ],
        [
            "Provide a clearer description of the intervention so "
            "the AI Manager can classify it under Scope 1, 2, or 3."
        ],
    )


def rule_eeg_advanced_tier(case: Case) -> Decision | None:
    """7. More than 350 tonnes of lifetime abatement. The AI's tonnes figure
    is only an estimate, so the proposal must also reach the minimum energy
    reduction (a claimed 400 tonnes with 0% reduction does not qualify)."""
    if not (
        case["lifetime_tonnes"] > EEG_ADVANCED_MIN_TONNES
        and case["energy_reduction_pct"] >= MINIMUM_IMPACT_PCT
    ):
        return None

    return _decision(
        "PRE_APPROVED_TIER_1_ADVANCED",
        [
            "Company meets the SME eligibility requirements.",
            f"Estimated lifetime carbon abatement of "
            f"{case['lifetime_tonnes']:.1f} tonnes exceeds the "
            "350-tonne Advanced Tier threshold.",
        ],
        [
            "Engage an independent energy assessor to verify the "
            "lifetime abatement estimate before final disbursement."
        ],
        [EEG_ADVANCED_NAME],
        calculate_subsidy(case["baseline_spend"], *EEG_ADVANCED_FUNDING),
    )


def rule_eeg_base_tier(case: Case) -> Decision | None:
    """8. Scope-1 fast track: at least 20% energy reduction."""
    if not (
        case["scope"] == "Scope-1"
        and case["energy_reduction_pct"] >= FAST_TRACK_MIN_PCT
    ):
        return None

    return _decision(
        "PRE_APPROVED_TIER_1",
        [
            "Company meets the SME eligibility requirements.",
            "Proposal targets Scope-1 emissions.",
            f"Estimated energy reduction of {case['energy_reduction_pct']:.1f}% "
            "meets the 20% threshold for this system's fast-track rule.",
        ],
        [],
        [EEG_BASE_NAME, ESP_NAME],
        calculate_subsidy(case["baseline_spend"], *EEG_BASE_FUNDING),
    )


def rule_esp_provisional(case: Case) -> Decision | None:
    """9. Any valid scope that misses the Scope-1 fast track but still
    reaches 15% (so Scope-1 at 15-20% lands here too)."""
    if case["energy_reduction_pct"] < PROVISIONAL_MIN_PCT:
        return None

    return _decision(
        "PROVISIONAL_APPROVAL_TIER_2",
        [
            "Company meets the SME eligibility requirements.",
            f"Proposal targets {case['scope']} emissions.",
            f"Estimated energy reduction of {case['energy_reduction_pct']:.1f}% "
            "meets the 15% threshold for provisional capability-support approval.",
        ],
        [
            "Prepare supporting baseline energy and emissions "
            "documentation for final assessment."
        ],
        [ESP_NAME],
        calculate_subsidy(case["baseline_spend"], *ESP_FUNDING),
    )


def rule_borderline_impact(case: Case) -> Decision | None:
    """10. 10% to under 15%: above the rejection line but below the
    provisional-approval line, so neither an automatic approval nor an
    automatic rejection is fair."""
    if not MINIMUM_IMPACT_PCT <= case["energy_reduction_pct"] < PROVISIONAL_MIN_PCT:
        return None

    return _decision(
        "MANUAL_REVIEW",
        [
            f"Estimated energy reduction of {case['energy_reduction_pct']:.1f}% meets the "
            f"minimum of {MINIMUM_IMPACT_PCT:.0f}% but is below the "
            f"{PROVISIONAL_MIN_PCT:.0f}% needed for provisional approval."
        ],
        [
            "Submit supporting baseline and measurement data so a "
            "reviewer can assess the proposal.",
            "Consider measures that raise the projected energy reduction "
            f"to at least {PROVISIONAL_MIN_PCT:.0f}%.",
        ],
    )


def rule_low_impact(case: Case) -> Decision:
    """11. Everything else: under 10% is rejected."""
    return _decision(
        "REJECT_LOW_IMPACT",
        [
            f"Estimated energy reduction of {case['energy_reduction_pct']:.1f}% "
            f"is below the minimum threshold of {MINIMUM_IMPACT_PCT:.1f}% "
            "used by this system."
        ],
        [
            "Consider increasing the projected energy-efficiency "
            "improvement to at least 15%.",
            "Consider additional energy-efficiency measures such "
            "as equipment upgrades, HVAC optimisation, lighting "
            "efficiency, or other applicable interventions.",
            "Recalculate the expected energy reduction after "
            "modifying the proposed project.",
        ],
    )


# First rule to return a decision wins, so this order IS the priority order.
DECISION_RULES = (
    rule_exclusion_keywords,
    rule_fossil_fuel_modification,
    rule_not_an_sme,
    rule_ai_failed,
    rule_reporting_without_fee,
    rule_reporting_grant,
    rule_missing_baseline_spend,
    rule_unclassified_scope,
    rule_eeg_advanced_tier,
    rule_eeg_base_tier,
    rule_esp_provisional,
    rule_borderline_impact,
    rule_low_impact,
)


# ---------------------------------------------------------
# Adjustments applied to whichever decision was chosen
# ---------------------------------------------------------


def cap_subsidy_at_retrofit_cost(decision: Decision, case: Case) -> None:
    """Equipment subsidies are worked out from the baseline energy spend, so
    a small retrofit could otherwise be "granted" more than it costs.
    (A cost of 0 means "not stated" and applies no cap.)"""
    retrofit_cost = case["retrofit_cost"]
    if (
        decision["decision_status"] in EQUIPMENT_SUBSIDY_STATUSES
        and 0 < retrofit_cost < decision["approved_subsidy_sgd"]
    ):
        decision["approved_subsidy_sgd"] = round(retrofit_cost, 2)
        decision["reasons"].append(
            f"Subsidy limited to the stated retrofit cost of SGD {retrofit_cost:,.2f}."
        )


def add_scheme_mismatch_note(decision: Decision, case: Case) -> None:
    """Tells the applicant if they picked a different scheme from the match."""
    if decision["decision_status"] in EQUIPMENT_SUBSIDY_STATUSES + (
        "PRE_APPROVED_SRG",
    ):
        note = scheme_mismatch_note(case["chosen_scheme"], decision["matched_schemes"])
        if note:
            decision["recommendations"].append(note)


def evaluate_grant_application(
    user_profile: dict[str, Any], ai_audit: dict[str, Any]
) -> dict[str, Any]:
    """
    Main Logic Layer function.

    Receives:
        user_profile:
            Financial and company information from the input layer.
            Expected keys: annual_revenue_sgd, group_employment_size,
            local_shareholding_pct, proposal_type, sustainability_grant,
            baseline_annual_energy_expenditure_sgd,
            estimated_retrofit_cost_sgd, reporting_advisory_fee_sgd.

        ai_audit:
            Structured information extracted by ai_manager.py.
            Expected keys: scope_category, estimated_energy_reduction_pct,
            estimated_lifetime_abatement_tonnes,
            detected_exclusion_keywords, primary_intervention_type.

    Returns a dict with: is_sme, decision_status, reasons, recommendations,
    matched_schemes, approved_subsidy_sgd and audit_passed.

    Priority order (highest first) is the order of DECISION_RULES:
        1. Exclusion keywords           -> manual exclusion review
        2. Fossil-fuel modification     -> manual exclusion review
        3. Not an SME                   -> statutory rejection
        4. ESG reporting / advisory     -> SRG (or manual review without a fee)
        5. No baseline energy spend     -> manual review
        6. GHG scope not classifiable   -> manual review
        7. EEG Advanced Tier (> 350 tonnes and >= 10% reduction)
        8. EEG Base Tier (Scope-1, >= 20% reduction)
        9. ESP provisional approval (any scope, >= 15% reduction)
       10. Manual review (10% to under 15% reduction)
       11. Reject - low impact (under 10% reduction)
    """

    case = build_case(user_profile, ai_audit)

    decision = None
    for rule in DECISION_RULES:
        decision = rule(case)
        if decision is not None:
            break

    cap_subsidy_at_retrofit_cost(decision, case)
    add_scheme_mismatch_note(decision, case)

    return {
        "is_sme": case["is_sme"],
        "decision_status": decision["decision_status"],
        "reasons": decision["reasons"],
        "recommendations": decision["recommendations"],
        "matched_schemes": decision["matched_schemes"],
        "approved_subsidy_sgd": decision["approved_subsidy_sgd"],
        "audit_passed": decision["decision_status"] in PASSING_STATUSES,
    }

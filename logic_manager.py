"""Logic Manager: every business rule of the grant auditor (no I/O, no AI).

Class overview
    LogicManager            facade the controller talks to
      PasswordHasher        owned by LogicManager   (composition)
      DecisionEngine        owned by LogicManager   (composition)
        EligibilityRule     abstract rule, 13 subclasses, injected (aggregation)
        DecisionAdjuster    abstract post-processor, 2 subclasses, injected
    GrantScheme             abstract funding scheme, 4 subclasses
    SmeCriteria             the statutory SME test
    CaseBuilder / Case      turns a profile + AI audit into the facts the rules use

Open/Closed: a new rule, scheme or adjustment is a new subclass handed to the
DecisionEngine. Nothing in DecisionEngine has to change.
"""

import hashlib
import hmac
import math
import secrets
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from models import REPORTING_PROPOSAL, EQUIPMENT_PROPOSAL, PlaceholderKeywords

Decision = dict[str, Any]  # what one rule returns

VALID_SCOPES = ["Scope-1", "Scope-2", "Scope-3"]

# Energy-reduction thresholds (percent), as in the project's rule set:
#   >= 20  Scope-1 fast-track (EEG Base Tier)
#   >= 15  provisional approval for any scope (ESP, 50% co-funding)
#   >= 10  below 15 but at least 10: referred to a person for review
#   <  10  rejected as insufficient decarbonisation yield
FAST_TRACK_MIN_PCT = 20.0
PROVISIONAL_MIN_PCT = 15.0
MINIMUM_IMPACT_PCT = 10.0
EEG_ADVANCED_MIN_TONNES = 350.0

# Decisions whose subsidy comes from the baseline energy spend (the
# reporting grant is based on the advisory fee instead).
EQUIPMENT_SUBSIDY_STATUSES = (
    "PRE_APPROVED_TIER_1",
    "PRE_APPROVED_TIER_1_ADVANCED",
    "PROVISIONAL_APPROVAL_TIER_2",
)
PASSING_STATUSES = EQUIPMENT_SUBSIDY_STATUSES + ("PRE_APPROVED_SRG",)

FOSSIL_FUEL_LABEL = "Fossil Fuel Modification"
EFS_GREEN_NAME = "Enterprise Financing Scheme – Green (EFS-Green)"


# =========================================================
# Password hashing (SHA-256 PBKDF2)
# =========================================================
class PasswordHasher:
    """Passwords are never stored. Instead we store a random 16-byte salt per
    user plus the PBKDF2-HMAC-SHA256 hash of salt + password, repeated
    `iterations` times so brute-forcing is slow. Comparison is constant time
    (hmac.compare_digest) so timing does not leak the hash."""

    ALGORITHM = "pbkdf2_sha256"
    DEFAULT_ITERATIONS = 200_000
    SALT_BYTES = 16
    # Upper limits used when checking a login, so a hand-edited or damaged
    # users.json (or an absurdly long password) cannot hang or crash the app.
    MAX_PASSWORD_CHARS_CHECKED = 256
    MAX_STORED_ITERATIONS = 5_000_000

    def __init__(self, iterations: int = DEFAULT_ITERATIONS) -> None:
        self._iterations = iterations

    def hash_password(
        self,
        password: str,
        salt_hex: str | None = None,
        iterations: int | None = None,
    ) -> dict[str, Any]:
        """Hashes a password. A fresh random salt is made for a new account;
        a stored salt is reused when checking a login.

        Returns: algorithm, iterations, salt (hex), password_hash (hex)."""
        if salt_hex is None:
            salt_hex = secrets.token_hex(self.SALT_BYTES)
        if iterations is None:
            iterations = self._iterations

        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
        )
        return {
            "algorithm": self.ALGORITHM,
            "iterations": iterations,
            "salt": salt_hex,
            "password_hash": digest.hex(),
        }
    def build_new_user_record(self, username: str, password: str) -> dict[str, Any]:
        """The record the Data Manager stores for a new account."""
        record: dict[str, Any] = {"username": username}
        record.update(self.hash_password(password))
        return record

    def verify_password(self, password: Any, user_record: Any) -> bool:
        """Checks a login attempt against a stored user record.

        user_record may be None (unknown username). A hash is still computed
        in that case so a wrong username takes as long as a wrong password.
        A damaged record simply fails the login instead of crashing."""
        if (
            not isinstance(password, str)
            or len(password) > self.MAX_PASSWORD_CHARS_CHECKED
        ):
            return False

        if not isinstance(user_record, dict):
            self.hash_password(password)  # dummy work to equalise timing
            return False

        salt = user_record.get("salt")
        stored_hash = user_record.get("password_hash")
        iterations = user_record.get("iterations", self.DEFAULT_ITERATIONS)

        if (
            not isinstance(salt, str)
            or not isinstance(stored_hash, str)
            or isinstance(iterations, bool)
            or not isinstance(iterations, int)
            or not 0 < iterations <= self.MAX_STORED_ITERATIONS
        ):
            return False

        try:
            attempt = self.hash_password(password, salt_hex=salt, iterations=iterations)
            return hmac.compare_digest(
                attempt["password_hash"].encode("ascii"), stored_hash.encode("ascii")
            )
        except (ValueError, TypeError, UnicodeError):
            return False


# =========================================================
# Funding schemes: one abstract idea, four concrete schemes
# =========================================================
class GrantScheme(ABC):
    """A funding scheme: a co-funding rate and a maximum subsidy in SGD."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def rate(self) -> float: ...

    @property
    @abstractmethod
    def cap(self) -> float: ...

    def calculate_subsidy(self, base_amount: float) -> float:
        """rate x base_amount, limited to the cap. Deterministic, no AI."""
        return round(min(base_amount * self.rate, self.cap), 2)


class EegAdvancedScheme(GrantScheme):
    name = "Energy Efficiency Grant (EEG) - Advanced Tier"
    rate = 0.70
    cap = 350_000.0


class EegBaseScheme(GrantScheme):
    name = "Energy Efficiency Grant (EEG) - Base Tier"
    rate = 0.70
    cap = 30_000.0


class EspScheme(GrantScheme):
    name = "Enterprise Sustainability Programme (ESP)"
    rate = 0.50
    cap = 20_000.0


class SrgScheme(GrantScheme):
    name = "Sustainability Reporting Grant (SRG)"
    rate = 0.30
    cap = 150_000.0


# =========================================================
# SME test
# =========================================================
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


# =========================================================
# Case: the facts a rule looks at
# =========================================================
@dataclass(frozen=True)
class Case:
    """The applicant's numbers plus the cleaned AI audit, with every missing
    or malformed value already replaced by a safe default."""

    # Company
    annual_revenue: float
    headcount: int
    local_equity: float
    is_sme: bool
    sme_fail_reasons: list[str] = field(default_factory=list)
    # Proposal (self-declared by the applicant, not inferred by the AI)
    proposal_type: str = EQUIPMENT_PROPOSAL
    chosen_scheme: Any = 0
    baseline_spend: float = 0.0
    retrofit_cost: float = 0.0
    advisory_fee: float = 0.0
    # AI audit
    scope: str = "Unknown"
    energy_reduction_pct: float = 0.0
    lifetime_tonnes: float = 0.0
    exclusions: list[str] = field(default_factory=list)
    intervention: str = ""
    ai_failed: bool = False


class CaseBuilder:
    """Builds a Case from the applicant's profile and the AI audit."""

    def __init__(self, sme_criteria: SmeCriteria | None = None) -> None:
        self._sme = sme_criteria or SmeCriteria()

    @staticmethod
    def number(value: Any, default: float = 0.0) -> float:
        """A finite float, or `default` for None, text, NaN or infinity.
        Keeps one bad value from crashing the whole evaluation."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        value = float(value)
        return value if math.isfinite(value) else default

    @staticmethod
    def string_list(value: Any) -> list[str]:
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
            if text and not PlaceholderKeywords.matches(text):
                items.append(text)
        return items

    def build(self, user_profile: dict[str, Any], ai_audit: dict[str, Any]) -> Case:
        annual_revenue = self.number(user_profile.get("annual_revenue_sgd"))
        headcount = int(self.number(user_profile.get("group_employment_size")))
        local_equity = self.number(user_profile.get("local_shareholding_pct"))

        return Case(
            annual_revenue=annual_revenue,
            headcount=headcount,
            local_equity=local_equity,
            is_sme=self._sme.is_sme(local_equity, annual_revenue, headcount),
            sme_fail_reasons=self._sme.fail_reasons(
                local_equity, annual_revenue, headcount
            ),
            proposal_type=user_profile.get("proposal_type", EQUIPMENT_PROPOSAL),
            chosen_scheme=user_profile.get("sustainability_grant", 0),
            baseline_spend=self.number(
                user_profile.get("baseline_annual_energy_expenditure_sgd")
            ),
            retrofit_cost=self.number(user_profile.get("estimated_retrofit_cost_sgd")),
            advisory_fee=self.number(user_profile.get("reporting_advisory_fee_sgd")),
            scope=ai_audit.get("scope_category", "Unknown"),
            energy_reduction_pct=self.number(
                ai_audit.get("estimated_energy_reduction_pct")
            ),
            lifetime_tonnes=self.number(
                ai_audit.get("estimated_lifetime_abatement_tonnes")
            ),
            exclusions=self.string_list(ai_audit.get("detected_exclusion_keywords")),
            intervention=ai_audit.get("primary_intervention_type", ""),
            ai_failed=str(ai_audit.get("ai_status", "ok")).strip().lower() == "failed",
        )


# =========================================================
# Eligibility rules
# =========================================================
class EligibilityRule(ABC):
    """One small rule. It either returns a decision or returns None to say
    "not mine". Every subclass is substitutable for this base (LSP): the same
    call, the same return type, no surprises for the engine."""

    @abstractmethod
    def evaluate(self, case: Case) -> Decision | None:
        """A decision when this rule applies, otherwise None."""

    @staticmethod
    def make_decision(
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


class ExclusionKeywordsRule(EligibilityRule):
    """Prohibited equipment named by the AI -> exclusion review."""

    def evaluate(self, case: Case) -> Decision | None:
        if not case.exclusions:
            return None

        reasons = [
            "Potentially prohibited equipment or modification was detected in the proposal."
        ]
        reasons += [f"Detected exclusion: {exclusion}" for exclusion in case.exclusions]

        return self.make_decision(
            "MANUAL_EXCLUSION_REVIEW",
            reasons,
            [
                "Remove the potentially prohibited equipment or modification from the proposal.",
                "Obtain a quotation for compliant, brand-new equipment where applicable.",
                "Resubmit the revised proposal for eligibility assessment.",
            ],
            ["Enterprise Sustainability Programme (Subject to re-quotation)"],
        )


class FossilFuelModificationRule(EligibilityRule):
    """Fossil-fuel modification may be an excluded activity."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.intervention != FOSSIL_FUEL_LABEL:
            return None

        return self.make_decision(
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


class NotAnSmeRule(EligibilityRule):
    """Statutory SME check. Rejection here outranks every approval path
    below it, including the reporting grant."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.is_sme:
            return None

        recommendations = [
            "Review the company's local shareholding structure and SME size criteria."
        ]
        if case.local_equity < SmeCriteria.MIN_LOCAL_EQUITY_PCT:
            recommendations.append(
                "Increase local shareholding to at least 30% "
                "if commercially and legally appropriate."
            )
        if case.annual_revenue > SmeCriteria.MAX_REVENUE_SGD:
            recommendations.append(
                "The company's revenue exceeds the SME cap of S$100 million. "
                "SME-targeted co-funding is therefore unavailable "
                "under these criteria."
            )
        recommendations.append(
            "Consider the Enterprise Financing Scheme – Green "
            "(EFS-Green) as an alternative financing route."
        )

        return self.make_decision(
            "REJECT_NON_SME", case.sme_fail_reasons, recommendations, [EFS_GREEN_NAME]
        )


class AiFailedRule(EligibilityRule):
    """The AI could not analyse the narrative, so no approval is safe."""

    def evaluate(self, case: Case) -> Decision | None:
        if not case.ai_failed:
            return None
        return self.make_decision(
            "MANUAL_REVIEW",
            reasons=[
                "The AI analysis failed, so the proposal could not be assessed automatically."
            ],
            recommendations=[
                "Run the analysis again, or send the proposal for manual review."
            ],
        )


class ReportingWithoutFeeRule(EligibilityRule):
    """The grant is a percentage of the fee, so no fee = nothing to approve."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.proposal_type != REPORTING_PROPOSAL or case.advisory_fee > 0:
            return None

        return self.make_decision(
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


class ReportingGrantRule(EligibilityRule):
    """Sustainability Reporting Grant (30% of the fee, capped)."""

    def __init__(self, scheme: GrantScheme | None = None) -> None:
        self._scheme = scheme or SrgScheme()

    def evaluate(self, case: Case) -> Decision | None:
        if case.proposal_type != REPORTING_PROPOSAL:
            return None

        return self.make_decision(
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
            [self._scheme.name],
            self._scheme.calculate_subsidy(case.advisory_fee),
        )


class MissingBaselineSpendRule(EligibilityRule):
    """Equipment subsidies come from the baseline energy spend, so a zero or
    missing value would otherwise pre-approve a SGD 0 subsidy."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.baseline_spend > 0:
            return None

        return self.make_decision(
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


class UnclassifiedScopeRule(EligibilityRule):
    """The AI could not place an equipment proposal in Scope 1, 2 or 3."""

    def evaluate(self, case: Case) -> Decision | None:
        if case.scope in VALID_SCOPES:
            return None

        return self.make_decision(
            "MANUAL_REVIEW",
            [
                f"GHG Protocol scope could not be determined (AI returned '{case.scope}')."
            ],
            [
                "Provide a clearer description of the intervention so "
                "the AI Manager can classify it under Scope 1, 2, or 3."
            ],
        )


class EegAdvancedTierRule(EligibilityRule):
    """More than 350 tonnes of lifetime abatement. The AI's tonnes figure is
    only an estimate, so the proposal must also reach the minimum energy
    reduction (a claimed 400 tonnes with 0% reduction does not qualify)."""

    def __init__(self, scheme: GrantScheme | None = None) -> None:
        self._scheme = scheme or EegAdvancedScheme()

    def evaluate(self, case: Case) -> Decision | None:
        if not (
            case.lifetime_tonnes > EEG_ADVANCED_MIN_TONNES
            and case.energy_reduction_pct >= MINIMUM_IMPACT_PCT
        ):
            return None

        return self.make_decision(
            "PRE_APPROVED_TIER_1_ADVANCED",
            [
                "Company meets the SME eligibility requirements.",
                f"Estimated lifetime carbon abatement of "
                f"{case.lifetime_tonnes:.1f} tonnes exceeds the "
                "350-tonne Advanced Tier threshold.",
            ],
            [
                "Engage an independent energy assessor to verify the "
                "lifetime abatement estimate before final disbursement."
            ],
            [self._scheme.name],
            self._scheme.calculate_subsidy(case.baseline_spend),
        )


class EegBaseTierRule(EligibilityRule):
    """Scope-1 fast track: at least 20% energy reduction."""

    def __init__(
        self,
        scheme: GrantScheme | None = None,
        companion_scheme: GrantScheme | None = None,
    ) -> None:
        self._scheme = scheme or EegBaseScheme()
        self._companion = companion_scheme or EspScheme()

    def evaluate(self, case: Case) -> Decision | None:
        if not (
            case.scope == "Scope-1" and case.energy_reduction_pct >= FAST_TRACK_MIN_PCT
        ):
            return None

        return self.make_decision(
            "PRE_APPROVED_TIER_1",
            [
                "Company meets the SME eligibility requirements.",
                "Proposal targets Scope-1 emissions.",
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% "
                "meets the 20% threshold for this system's fast-track rule.",
            ],
            [],
            [self._scheme.name, self._companion.name],
            self._scheme.calculate_subsidy(case.baseline_spend),
        )


class EspProvisionalRule(EligibilityRule):
    """Any valid scope that misses the Scope-1 fast track but still reaches
    15% (so Scope-1 at 15-20% lands here too)."""

    def __init__(self, scheme: GrantScheme | None = None) -> None:
        self._scheme = scheme or EspScheme()

    def evaluate(self, case: Case) -> Decision | None:
        if case.energy_reduction_pct < PROVISIONAL_MIN_PCT:
            return None

        return self.make_decision(
            "PROVISIONAL_APPROVAL_TIER_2",
            [
                "Company meets the SME eligibility requirements.",
                f"Proposal targets {case.scope} emissions.",
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% "
                "meets the 15% threshold for provisional capability-support approval.",
            ],
            [
                "Prepare supporting baseline energy and emissions "
                "documentation for final assessment."
            ],
            [self._scheme.name],
            self._scheme.calculate_subsidy(case.baseline_spend),
        )


class BorderlineImpactRule(EligibilityRule):
    """10% to under 15%: above the rejection line but below the provisional
    approval line, so neither an automatic approval nor an automatic
    rejection is fair."""

    def evaluate(self, case: Case) -> Decision | None:
        if not MINIMUM_IMPACT_PCT <= case.energy_reduction_pct < PROVISIONAL_MIN_PCT:
            return None

        return self.make_decision(
            "MANUAL_REVIEW",
            [
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% meets the "
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


class LowImpactRule(EligibilityRule):
    """Everything else: under 10% is rejected. This rule never returns None,
    so it is the catch-all that ends every rule list."""

    def evaluate(self, case: Case) -> Decision:
        return self.make_decision(
            "REJECT_LOW_IMPACT",
            [
                f"Estimated energy reduction of {case.energy_reduction_pct:.1f}% "
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


# =========================================================
# Adjustments applied to whichever decision was chosen
# =========================================================
class DecisionAdjuster(ABC):
    """A step applied to the chosen decision after the rules have run."""

    @abstractmethod
    def adjust(self, decision: Decision, case: Case) -> None: ...


class RetrofitCostCap(DecisionAdjuster):
    """Equipment subsidies are worked out from the baseline energy spend, so
    a small retrofit could otherwise be "granted" more than it costs.
    (A cost of 0 means "not stated" and applies no cap.)"""

    def adjust(self, decision: Decision, case: Case) -> None:
        if (
            decision["decision_status"] in EQUIPMENT_SUBSIDY_STATUSES
            and 0 < case.retrofit_cost < decision["approved_subsidy_sgd"]
        ):
            decision["approved_subsidy_sgd"] = round(case.retrofit_cost, 2)
            decision["reasons"].append(
                f"Subsidy limited to the stated retrofit cost of SGD {case.retrofit_cost:,.2f}."
            )


class SchemeMismatchNote(DecisionAdjuster):
    """Tells the applicant if they picked a different scheme from the match.
    Informational only: the decision itself is never changed."""

    # Menu text chosen by the applicant -> the scheme name the rules produce.
    # Other choices (e.g. Enterprise Development Grant, "Others") have no
    # matching rule, so they are never flagged.
    KEYWORDS = (
        ("advanced tier", EegAdvancedScheme.name),
        ("base tier", EegBaseScheme.name),
        ("reporting", SrgScheme.name),
    )

    def note_for(self, chosen_scheme: Any, matched_schemes: list[str]) -> str | None:
        """A recommendation when the scheme the applicant picked is not the
        one the rules matched, otherwise None."""
        if not isinstance(chosen_scheme, str) or not matched_schemes:
            return None

        lowered = chosen_scheme.lower()
        for keyword, expected_scheme in self.KEYWORDS:
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

    def adjust(self, decision: Decision, case: Case) -> None:
        if decision["decision_status"] in PASSING_STATUSES:
            note = self.note_for(case.chosen_scheme, decision["matched_schemes"])
            if note:
                decision["recommendations"].append(note)


# =========================================================
# Decision engine
# =========================================================
class DecisionEngine:
    """Runs the rules in order; the first rule to return a decision wins, so
    the ORDER of the rules is the priority order of the grant rules. The rules
    and adjusters are handed in (aggregation): they exist without the engine
    and can be swapped or extended without editing it."""

    def __init__(
        self,
        rules: Sequence[EligibilityRule],
        adjusters: Sequence[DecisionAdjuster] = (),
    ) -> None:
        self._rules = tuple(rules)
        self._adjusters = tuple(adjusters)

    @classmethod
    def with_default_rules(cls) -> "DecisionEngine":
        """The project's rule set, highest priority first."""
        return cls(
            rules=[
                ExclusionKeywordsRule(),
                FossilFuelModificationRule(),
                NotAnSmeRule(),
                AiFailedRule(),
                ReportingWithoutFeeRule(),
                ReportingGrantRule(),
                MissingBaselineSpendRule(),
                UnclassifiedScopeRule(),
                EegAdvancedTierRule(),
                EegBaseTierRule(),
                EspProvisionalRule(),
                BorderlineImpactRule(),
                LowImpactRule(),
            ],
            adjusters=[RetrofitCostCap(), SchemeMismatchNote()],
        )

    @property
    def rules(self) -> tuple[EligibilityRule, ...]:
        return self._rules

    def decide(self, case: Case) -> Decision:
        decision = None
        for rule in self._rules:
            decision = rule.evaluate(case)
            if decision is not None:
                break
        if decision is None:
            raise LookupError("No eligibility rule produced a decision.")

        for adjuster in self._adjusters:
            adjuster.adjust(decision, case)
        return decision


# =========================================================
# The Logic Manager
# =========================================================
class LogicManager:
    """The Logic Manager as the controller sees it. It owns a PasswordHasher
    and a CaseBuilder (composition: they are created here and live and die
    with it) and uses a DecisionEngine that may be supplied (aggregation)."""

    def __init__(self, engine: DecisionEngine | None = None) -> None:
        self._hasher = PasswordHasher()
        self._case_builder = CaseBuilder()
        self._sme = SmeCriteria()
        self._mismatch = SchemeMismatchNote()
        self._engine = engine or DecisionEngine.with_default_rules()

    @property
    def engine(self) -> DecisionEngine:
        return self._engine

    # ----- passwords -----
    def hash_password(
        self,
        password: str,
        salt_hex: str | None = None,
        iterations: int | None = None,
    ) -> dict[str, Any]:
        return self._hasher.hash_password(password, salt_hex, iterations)

    def build_new_user_record(self, username: str, password: str) -> dict[str, Any]:
        return self._hasher.build_new_user_record(username, password)

    def verify_password(self, password: Any, user_record: Any) -> bool:
        return self._hasher.verify_password(password, user_record)

    # ----- SME test and subsidy -----
    def check_sme_status(
        self, local_equity_pct: float, annual_revenue: float, headcount: int
    ) -> bool:
        return self._sme.is_sme(local_equity_pct, annual_revenue, headcount)

    def get_sme_fail_reasons(
        self, local_equity_pct: float, annual_revenue: float, headcount: int
    ) -> list[str]:
        return self._sme.fail_reasons(local_equity_pct, annual_revenue, headcount)

    def scheme_mismatch_note(
        self, chosen_scheme: Any, matched_schemes: list[str]
    ) -> str | None:
        return self._mismatch.note_for(chosen_scheme, matched_schemes)

    # ----- decisions -----
    def build_case(
        self, user_profile: dict[str, Any], ai_audit: dict[str, Any]
    ) -> Case:
        return self._case_builder.build(user_profile, ai_audit)

    def evaluate_grant_application(
        self, user_profile: dict[str, Any], ai_audit: dict[str, Any]
    ) -> dict[str, Any]:
        """Main Logic Layer entry point.

        user_profile: the applicant's company and proposal details (from the
            I/O layer). ai_audit: the structured result from the AI Manager.

        Returns a dict with: is_sme, decision_status, reasons,
        recommendations, matched_schemes, approved_subsidy_sgd, audit_passed.

        Priority order (highest first) is the order of the engine's rules:
            1. Exclusion keywords           -> manual exclusion review
            2. Fossil-fuel modification     -> manual exclusion review
            3. Not an SME                   -> statutory rejection
            4. AI analysis failed           -> manual review
            5. ESG reporting / advisory     -> SRG (or manual review without a fee)
            6. No baseline energy spend     -> manual review
            7. GHG scope not classifiable   -> manual review
            8. EEG Advanced Tier (> 350 tonnes and >= 10% reduction)
            9. EEG Base Tier (Scope-1, >= 20% reduction)
           10. ESP provisional approval (any scope, >= 15% reduction)
           11. Manual review (10% to under 15% reduction)
           12. Reject - low impact (under 10% reduction)
        """
        case = self.build_case(user_profile, ai_audit)
        decision = self._engine.decide(case)

        return {
            "is_sme": case.is_sme,
            "decision_status": decision["decision_status"],
            "reasons": decision["reasons"],
            "recommendations": decision["recommendations"],
            "matched_schemes": decision["matched_schemes"],
            "approved_subsidy_sgd": decision["approved_subsidy_sgd"],
            "audit_passed": decision["decision_status"] in PASSING_STATUSES,
        }

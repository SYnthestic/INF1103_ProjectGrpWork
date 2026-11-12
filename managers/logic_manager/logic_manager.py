"""LogicManager: the Logic Manager as the controller sees it."""

import os
from typing import Any

from models import FileCipher
from .constants import PASSING_STATUSES
from .access_policy import AccessPolicy
from .aes_gcm_cipher import AesGcmCipher
from .case import Case
from .case_builder import CaseBuilder
from .decision_engine import DecisionEngine
from .password_hasher import PasswordHasher
from .rule_config import RuleConfig
from .adjusters.scheme_mismatch_note import SchemeMismatchNote
from .sme_criteria import SmeCriteria


class LogicManager:
    """The Logic Manager as the controller sees it. It owns a PasswordHasher,
    a CaseBuilder and an AccessPolicy (composition: they are created here and
    live and die with it) and uses a DecisionEngine that may be supplied
    (aggregation)."""

    def __init__(
        self,
        engine: DecisionEngine | None = None,
        rule_config: RuleConfig | None = None,
        admin_username: str | None = None,
    ) -> None:
        self._hasher = PasswordHasher()
        self._case_builder = CaseBuilder()
        self._sme = SmeCriteria()
        self._mismatch = SchemeMismatchNote()
        self._rule_config = rule_config or RuleConfig()
        # A supplied engine is kept as it is; the default one is rebuilt
        # whenever the thresholds change.
        self._custom_engine = engine is not None
        self._engine = engine or DecisionEngine.with_default_rules(self._rule_config)
        if admin_username is None:
            admin_username = os.environ.get("ADMIN_USERNAME")
        self._access = AccessPolicy(admin_username)
        # Created when first needed, so the grant rules work without a key.
        self._file_cipher: FileCipher | None = None

    @property
    def engine(self) -> DecisionEngine:
        return self._engine

    # ----- file encryption -----
    @property
    def file_cipher(self) -> FileCipher:
        """AES cipher for the data files (composition: LogicManager owns it).
        Raises EncryptionKeyError if the key is missing or invalid."""
        if self._file_cipher is None:
            self._file_cipher = AesGcmCipher.from_environment()
        return self._file_cipher

    @staticmethod
    def generate_encryption_key() -> str:
        return AesGcmCipher.generate_key()

    # ----- adjustable thresholds -----
    @property
    def rule_config(self) -> RuleConfig:
        return self._rule_config

    def use_rule_config(self, config: RuleConfig) -> None:
        """Every later decision uses these thresholds."""
        self._rule_config = config
        if not self._custom_engine:
            self._engine = DecisionEngine.with_default_rules(config)

    @staticmethod
    def default_rule_config() -> RuleConfig:
        return RuleConfig()

    @staticmethod
    def rule_config_problems(values: Any) -> list[str]:
        return RuleConfig.problems(values)

    @staticmethod
    def rule_config_from_dict(values: Any) -> RuleConfig:
        """Raises ValueError (listing the problems) for invalid settings."""
        return RuleConfig.from_dict(values)

    # ----- administrator access -----
    @property
    def access(self) -> AccessPolicy:
        return self._access

    def is_admin(self, username: str, user_record: Any) -> bool:
        return self._access.is_admin(username, user_record)

    # ----- passwords -----
    def hash_password(
        self,
        password: str,
        salt_hex: str | None = None,
        iterations: int | None = None,
    ) -> dict[str, Any]:
        return self._hasher.hash_password(password, salt_hex, iterations)

    def build_new_user_record(
        self, username: str, password: str, role: str = AccessPolicy.USER
    ) -> dict[str, Any]:
        """A new account to store: the password hash plus the role (accounts
        made on the login screen are always ordinary users)."""
        if role not in AccessPolicy.ROLES:
            raise ValueError(f"Unknown role '{role}'.")
        record = self._hasher.build_new_user_record(username, password)
        record["role"] = role
        return record

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

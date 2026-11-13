"""Raw model text -> validated, correctly typed audit dict."""

import copy
import json
import logging
import math
import re
from typing import Any

from .ai_config import DEFAULT_AI_AUDIT, AiAudit
from models import PlaceholderKeywords

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class AuditResponseParser:
    """Turns whatever the model returned into the exact schema the Logic
    Manager expects, falling back to safe defaults field by field."""

    @staticmethod
    def default_audit() -> AiAudit:
        return copy.deepcopy(DEFAULT_AI_AUDIT)

    @classmethod
    def unusable_answer(cls, reason: str) -> AiAudit:
        logger.warning(
            "AI answer could not be used (%s); using fallback defaults.", reason
        )
        return cls.default_audit()

    @classmethod
    def parse(cls, raw_content: Any) -> AiAudit:
        if not isinstance(raw_content, str):
            return cls.unusable_answer("the answer was not text")

        cleaned = raw_content.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start == -1 or end <= start:
                return cls.unusable_answer("no JSON object found")
            try:
                parsed = json.loads(cleaned[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                return cls.unusable_answer("invalid JSON")

        if not isinstance(parsed, dict):
            return cls.unusable_answer("JSON was not an object")

        return cls.sanitise(parsed)

    @classmethod
    def sanitise(cls, parsed: Any) -> AiAudit:
        if not isinstance(parsed, dict):
            return cls.default_audit()
        audit = cls.default_audit()
        audit["scope_category"] = cls.to_scope(parsed.get("scope_category"))
        audit["primary_intervention_type"] = cls.to_text(
            parsed.get("primary_intervention_type")
        )
        audit["estimated_energy_reduction_pct"] = cls.to_number(
            parsed.get("estimated_energy_reduction_pct"), 0.0, 0.0, 100.0
        )
        audit["estimated_lifetime_abatement_tonnes"] = cls.to_number(
            parsed.get("estimated_lifetime_abatement_tonnes"), 0.0, 0.0
        )
        audit["detected_exclusion_keywords"] = cls.to_string_list(
            parsed.get("detected_exclusion_keywords")
        )
        audit["implementation_bottleneck"] = cls.to_text(
            parsed.get("implementation_bottleneck")
        )
        audit["ai_reasoning_summary"] = cls.to_text(
            parsed.get("ai_reasoning_summary"),
            DEFAULT_AI_AUDIT["ai_reasoning_summary"],
        )
        audit["ai_status"] = "ok"
        return audit

    @staticmethod
    def to_number(
        value: Any,
        default: float = 0.0,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        if isinstance(value, bool):
            return default
        if isinstance(value, str):
            match = re.search(r"-?\d[\d,]*\.?\d*|-?\.\d+", value)
            if not match:
                return default
            try:
                value = float(match.group().replace(",", ""))
            except ValueError:
                return default
        if not isinstance(value, (int, float)):
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        if minimum is not None:
            number = max(number, minimum)
        if maximum is not None:
            number = min(number, maximum)
        return number

    @staticmethod
    def to_text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        return value.strip() if isinstance(value, str) else str(value)

    @staticmethod
    def to_scope(value: Any) -> str:
        if isinstance(value, str):
            match = re.fullmatch(r"\s*scope[\s_-]*([123])\s*", value, re.IGNORECASE)
            if match:
                return f"Scope-{match.group(1)}"
        return "Unknown"

    @staticmethod
    def to_string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            value = re.split(r"[,;\n]", value)
        if not isinstance(value, (list, tuple)):
            return []
        items = []
        for item in value:
            if item is None or isinstance(item, (dict, list, tuple)):
                continue
            text = str(item).strip()
            if text and not PlaceholderKeywords.matches(text):
                items.append(text)
        return items
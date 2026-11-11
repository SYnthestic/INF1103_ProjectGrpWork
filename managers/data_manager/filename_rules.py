"""FilenameRules: what counts as a safe save-file or PDF name."""

import os
import re


class FilenameRules:
    """What counts as a safe save-file or PDF name."""

    INVALID_CHARS = '/\\:*?"<>|'

    @staticmethod
    def normalise(jsonfile_name: str | None) -> str:
        """Strips whitespace and makes sure the name ends with .json
        (any capitalisation of the extension is accepted)."""
        if jsonfile_name is None:
            return ""
        jsonfile_name = str(jsonfile_name).strip()
        if jsonfile_name and not jsonfile_name.lower().endswith(".json"):
            jsonfile_name += ".json"
        return jsonfile_name


    @classmethod
    def is_valid(cls, jsonfile_name: str) -> bool:
        """A bare filename only: no folders, control characters, or empty stem."""
        if any(char in jsonfile_name for char in cls.INVALID_CHARS):
            return False
        if any(ord(char) < 32 for char in jsonfile_name):
            return False
        stem = (
            jsonfile_name[: -len(".json")]
            if jsonfile_name.lower().endswith(".json")
            else jsonfile_name
        )
        # Rejects ".json", "..json", " .json" and similar nameless files.
        return stem.strip(" .") != ""

    @classmethod
    def company_save_filename(cls, company_name: str) -> str:
        """A stable, safe JSON filename for one company. Repeated assessments
        for the same company use the same name; different companies differ."""
        company_name = str(company_name or "Company").strip()
        safe_name = "".join(
            "_" if char in cls.INVALID_CHARS or ord(char) < 32 else char
            for char in company_name
        )
        safe_name = re.sub(r"\s+", " ", safe_name).strip(" .")[:100].rstrip(" .")
        if not safe_name:
            safe_name = "Company"
        return f"audit_{safe_name}.json"

    @classmethod
    def resolve_pdf_name(cls, source_name: str, pdf_filename: str | None) -> str | None:
        """The PDF file name to use, or None when it is not a safe name."""
        if pdf_filename is None or not str(pdf_filename).strip():
            pdf_name = os.path.splitext(source_name)[0] + ".pdf"
        else:
            pdf_name = str(pdf_filename).strip()
            if not pdf_name.lower().endswith(".pdf"):
                pdf_name += ".pdf"

        pdf_stem = os.path.splitext(pdf_name)[0]
        if (
            not pdf_stem.strip(" .")
            or os.path.basename(pdf_name) != pdf_name
            or any(char in pdf_name for char in cls.INVALID_CHARS)
            or any(ord(char) < 32 for char in pdf_name)
        ):
            return None
        return pdf_name

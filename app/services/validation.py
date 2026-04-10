"""
Input validation for resume analysis requests.
SPEC: Input Validation section.
"""

VALID_SENIORITIES = {"intern", "entry_level", "mid_level", "senior", "executive"}
MIN_RESUME_LENGTH = 50
MAX_RESUME_LENGTH = 50000


class ValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_input(resume_text: str, target_seniority: str, target_noc_code: str):
    if not resume_text or len(resume_text) < MIN_RESUME_LENGTH:
        raise ValidationError("INVALID_INPUT", f"resume_text must be at least {MIN_RESUME_LENGTH} characters")

    if len(resume_text) > MAX_RESUME_LENGTH:
        raise ValidationError("INVALID_INPUT", f"resume_text must be at most {MAX_RESUME_LENGTH} characters")

    if target_seniority not in VALID_SENIORITIES:
        raise ValidationError("INVALID_SENIORITY", f"target_seniority must be one of: {', '.join(sorted(VALID_SENIORITIES))}")

    if not target_noc_code or not target_noc_code.isdigit() or len(target_noc_code) != 5:
        raise ValidationError("INVALID_NOC", "target_noc_code must be a 5-digit NOC code")

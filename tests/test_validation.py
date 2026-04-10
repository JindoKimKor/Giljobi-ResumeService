"""
Tests for input validation.
SPEC: Input Validation section — resume length, seniority set, noc format.
"""

import pytest

from app.services.validation import validate_input, ValidationError, VALID_SENIORITIES


class TestResumeValidation:
    """SPEC: resume_text min 50 chars, max 50,000 chars."""

    def test_valid_resume(self):
        validate_input(resume_text="x" * 100, target_seniority="senior", target_noc_code="21231")

    def test_resume_too_short(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="short", target_seniority="senior", target_noc_code="21231")
        assert exc.value.code == "INVALID_INPUT"

    def test_resume_too_long(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="x" * 60000, target_seniority="senior", target_noc_code="21231")
        assert exc.value.code == "INVALID_INPUT"

    def test_resume_exactly_50_chars(self):
        validate_input(resume_text="x" * 50, target_seniority="senior", target_noc_code="21231")

    def test_resume_empty(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="", target_seniority="senior", target_noc_code="21231")
        assert exc.value.code == "INVALID_INPUT"


class TestSeniorityValidation:
    """SPEC: one of intern, entry_level, mid_level, senior, executive."""

    def test_valid_seniorities(self):
        for s in ["intern", "entry_level", "mid_level", "senior", "executive"]:
            validate_input(resume_text="x" * 100, target_seniority=s, target_noc_code="21231")

    def test_invalid_seniority(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="x" * 100, target_seniority="manager", target_noc_code="21231")
        assert exc.value.code == "INVALID_SENIORITY"

    def test_empty_seniority(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="x" * 100, target_seniority="", target_noc_code="21231")
        assert exc.value.code == "INVALID_SENIORITY"


class TestNocValidation:
    """SPEC: 5-digit NOC code format."""

    def test_valid_noc_code(self):
        validate_input(resume_text="x" * 100, target_seniority="senior", target_noc_code="21231")

    def test_invalid_noc_format_letters(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="x" * 100, target_seniority="senior", target_noc_code="abc")
        assert exc.value.code == "INVALID_NOC"

    def test_invalid_noc_format_too_short(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="x" * 100, target_seniority="senior", target_noc_code="212")
        assert exc.value.code == "INVALID_NOC"

    def test_invalid_noc_empty(self):
        with pytest.raises(ValidationError) as exc:
            validate_input(resume_text="x" * 100, target_seniority="senior", target_noc_code="")
        assert exc.value.code == "INVALID_NOC"


class TestConstants:
    def test_valid_seniorities_set(self):
        assert VALID_SENIORITIES == {"intern", "entry_level", "mid_level", "senior", "executive"}

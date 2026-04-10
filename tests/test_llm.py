"""
Tests for Claude CLI LLM wrapper.
SPEC: LLM Prompts section — extract skills, generate analysis.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.llm import extract_skills, reconcile_skills, generate_analysis, LLMError


class TestExtractSkills:
    """SPEC: Prompt 1 — Resume → skills extraction."""

    @patch("app.services.llm.subprocess.run")
    def test_valid_resume_returns_skills(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='["python", "aws", "docker"]', stderr="")
        result = extract_skills("Experienced engineer with Python, AWS, Docker...")
        assert result == ["python", "aws", "docker"]

    @patch("app.services.llm.subprocess.run")
    def test_empty_skills(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='[]', stderr="")
        result = extract_skills("No technical skills mentioned")
        assert result == []

    @patch("app.services.llm.subprocess.run")
    def test_invalid_json_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json at all", stderr="")
        with pytest.raises(LLMError):
            extract_skills("Some resume text")

    @patch("app.services.llm.subprocess.run")
    def test_cli_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        with pytest.raises(LLMError):
            extract_skills("Some resume text")

    @patch("app.services.llm.subprocess.run")
    def test_json_with_preamble(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='Here is the result:\n["python", "sql"]', stderr="")
        result = extract_skills("Resume with Python and SQL")
        assert result == ["python", "sql"]


class TestReconcileSkills:
    """SPEC: Prompt 2 — Reconcile against DB skills."""

    @patch("app.services.llm.subprocess.run")
    def test_valid_reconcile(self, mock_run):
        response = '{"matched": ["python", "sql"], "missing": ["kubernetes"]}'
        mock_run.return_value = MagicMock(returncode=0, stdout=response, stderr="")
        result = reconcile_skills("Resume with Python and SQL", {
            "hard_skill": ["python", "sql", "kubernetes"],
        })
        assert result["matched"] == ["python", "sql"]
        assert result["missing"] == ["kubernetes"]

    @patch("app.services.llm.subprocess.run")
    def test_invalid_json_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        with pytest.raises(LLMError):
            reconcile_skills("Resume", {"hard_skill": ["python"]})

    @patch("app.services.llm.subprocess.run")
    def test_empty_result(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"matched": [], "missing": ["python"]}', stderr="")
        result = reconcile_skills("No skills", {"hard_skill": ["python"]})
        assert result["matched"] == []
        assert result["missing"] == ["python"]


class TestGenerateAnalysis:
    """SPEC: Prompt 3 — Gap analysis + JD highlight."""

    @patch("app.services.llm.subprocess.run")
    def test_valid_analysis(self, mock_run):
        response = '{"strengths": ["Good backend"], "gaps": ["K8s missing"], "recommendations": "Learn K8s", "jd_highlighted": "Looking for [✅ Python]"}'
        mock_run.return_value = MagicMock(returncode=0, stdout=response, stderr="")
        result = generate_analysis(
            all_user_skills=["python"],
            noc_name="Software engineers",
            matched_skills=["python"],
            missing_skills=["kubernetes"],
            match_rate=0.78,
            company="Google",
            title="Senior SWE",
            description="Looking for Python and K8s"
        )
        assert "strengths" in result
        assert "gaps" in result
        assert "recommendations" in result
        assert "jd_highlighted" in result

    @patch("app.services.llm.subprocess.run")
    def test_invalid_json_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        with pytest.raises(LLMError):
            generate_analysis(
                all_user_skills=[], noc_name="", matched_skills=[], missing_skills=[],
                match_rate=0, company="", title="", description=""
            )

    @patch("app.services.llm.subprocess.run")
    def test_cli_failure_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")
        with pytest.raises(LLMError):
            generate_analysis(
                all_user_skills=[], noc_name="", matched_skills=[], missing_skills=[],
                match_rate=0, company="", title="", description=""
            )

"""
Tests for skill matching logic.
SPEC: DB 쿼리 section + Section 1-3 matching.
"""

import pytest

from app.services.matcher import calculate_match_rate


class TestCalculateMatchRate:
    """Pure logic — no DB dependency."""

    def test_partial_match(self):
        result = calculate_match_rate(
            user_skills=["python", "aws"],
            required_skills=["python", "aws", "kubernetes"]
        )
        assert abs(result["match_rate"] - 0.667) < 0.01
        assert set(result["matched"]) == {"python", "aws"}
        assert set(result["missing"]) == {"kubernetes"}
        assert result["total_required"] == 3

    def test_no_overlap(self):
        result = calculate_match_rate(
            user_skills=["go", "rust"],
            required_skills=["python", "aws"]
        )
        assert result["match_rate"] == 0.0
        assert result["matched"] == []
        assert set(result["missing"]) == {"python", "aws"}

    def test_full_match(self):
        result = calculate_match_rate(
            user_skills=["python", "aws", "docker"],
            required_skills=["python", "aws"]
        )
        assert result["match_rate"] == 1.0
        assert set(result["matched"]) == {"python", "aws"}
        assert result["missing"] == []

    def test_empty_user_skills(self):
        result = calculate_match_rate(
            user_skills=[],
            required_skills=["python", "aws"]
        )
        assert result["match_rate"] == 0.0
        assert result["matched"] == []

    def test_empty_required_skills(self):
        result = calculate_match_rate(
            user_skills=["python"],
            required_skills=[]
        )
        assert result["match_rate"] == 0.0
        assert result["matched"] == []

    def test_case_insensitive(self):
        result = calculate_match_rate(
            user_skills=["Python", "AWS"],
            required_skills=["python", "aws", "docker"]
        )
        assert abs(result["match_rate"] - 0.667) < 0.01
        assert len(result["matched"]) == 2

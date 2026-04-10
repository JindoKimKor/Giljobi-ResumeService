"""
Claude CLI subprocess wrapper.
SPEC: LLM Prompts section + Claude CLI Invocation.
"""

import json
import os
import re
import subprocess


class LLMError(Exception):
    pass


SKILL_EXTRACT_PROMPT = """Extract all technical skills, tools, and certifications from this resume.
Return ONLY a JSON array of lowercase strings. No explanation.

Example output: ["python", "aws", "docker", "sql", "kubernetes", "ci/cd"]

Resume:
{resume_text}"""

ANALYSIS_PROMPT = """You are a career analyst. Given a candidate's skills, their match against a target job category, and a real job posting, provide:

1. strengths: List of 2-4 bullet points about the candidate's strong areas relative to market demand
2. gaps: List of 2-4 specific skill gaps with market demand percentage (e.g. "Kubernetes — 82% of JDs require")
3. recommendations: 1-2 sentences of actionable advice
4. jd_highlighted: The job description with matched skills marked as [✅ skill] and missing skills as [❌ skill]

Return as JSON:
{{
  "strengths": ["..."],
  "gaps": ["..."],
  "recommendations": "...",
  "jd_highlighted": "..."
}}

Candidate skills: {user_skills}
Target NOC: {noc_name} ({noc_code})
Match rate: {match_rate}
Matched skills: {matched_skills}
Missing skills: {missing_skills}

Best matching job posting:
Company: {company}
Title: {title}
Description:
{description}"""


def _call_claude(prompt: str) -> str:
    """Call Claude CLI via subprocess and return stdout."""
    result = subprocess.run(
        ["claude", "--print", "--model", "haiku", "-"],
        input=prompt,
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": os.environ.get("CLAUDE_HOME", os.path.expanduser("~"))}
    )
    if result.returncode != 0:
        raise LLMError(f"Claude CLI failed (exit {result.returncode}): {result.stderr}")
    return result.stdout


def _parse_json(text: str):
    """Extract JSON from text that may contain preamble."""
    match = re.search(r'[\[\{].*[\]\}]', text, re.DOTALL)
    if not match:
        raise LLMError(f"No JSON found in LLM response: {text[:200]}")
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        raise LLMError(f"Invalid JSON in LLM response: {e}")


def extract_skills(resume_text: str) -> list[str]:
    """SPEC Prompt 1: Resume → skills extraction."""
    prompt = SKILL_EXTRACT_PROMPT.format(resume_text=resume_text)
    stdout = _call_claude(prompt)
    return _parse_json(stdout)


def generate_analysis(
    user_skills: list[str],
    noc_name: str,
    noc_code: str,
    match_rate: float,
    matched_skills: list[str],
    missing_skills: list[str],
    company: str,
    title: str,
    description: str,
) -> dict:
    """SPEC Prompt 2: Gap analysis + JD highlight."""
    prompt = ANALYSIS_PROMPT.format(
        user_skills=", ".join(user_skills),
        noc_name=noc_name,
        noc_code=noc_code,
        match_rate=f"{match_rate:.0%}",
        matched_skills=", ".join(matched_skills),
        missing_skills=", ".join(missing_skills),
        company=company,
        title=title,
        description=description,
    )
    stdout = _call_claude(prompt)
    return _parse_json(stdout)

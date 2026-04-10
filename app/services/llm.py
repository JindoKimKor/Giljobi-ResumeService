"""
Claude CLI subprocess wrapper — 3 prompts.
SPEC: LLM Prompts section.
"""

import json
import os
import re
import subprocess


class LLMError(Exception):
    pass


# ── Prompt Templates ──

SKILL_EXTRACT_PROMPT = """Extract all technical skills, tools, and certifications from this resume.
Return ONLY a JSON array of lowercase strings. No explanation.

Example output: ["python", "aws", "docker", "sql", "kubernetes", "ci/cd"]

Resume:
{resume_text}"""

RECONCILE_PROMPT = """Given a resume and a list of skills from a job category database, identify which skills the candidate has.

IMPORTANT: Return ONLY skills from the provided list. Use the EXACT names from the list.
Do not add skills that are not in the list. Do not modify skill names.

Skills list (from database):
Hard Skills: {hard_skills}
Soft Skills: {soft_skills}
Tools: {tools}
Certifications: {certifications}

Return a JSON object with matched and missing skills:
{{
  "matched": ["skill1", "skill2"],
  "missing": ["skill3", "skill4"]
}}

Resume:
{resume_text}"""

FORMAT_JD_PROMPT = """Reformat this raw job description into a clean, well-structured format.

Rules:
- Extract and clearly label: Role/Title, Location, Duration/Type, Required Experience, Tech Stack, Responsibilities, Requirements, Nice-to-haves
- Only include sections that exist in the original — do not invent information
- Use bullet points (- ) for lists, not bullets or asterisks
- Keep it concise but complete

Return ONLY the formatted text as Markdown. No JSON, no preamble.

Raw job description:
{description}"""

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

Candidate's extracted skills (free extraction): {all_user_skills}
Matched against DB ({noc_name}): {matched_skills}
Missing from DB: {missing_skills}
Match rate: {match_rate}

Best matching job posting:
Company: {company}
Title: {title}
Description:
{description}"""


# ── Claude CLI ──

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


# ── Prompt 1: Free Skill Extraction (Stage 2) ──

def extract_skills(resume_text: str) -> list[str]:
    """Extract skills freely from resume text."""
    prompt = SKILL_EXTRACT_PROMPT.format(resume_text=resume_text)
    stdout = _call_claude(prompt)
    return _parse_json(stdout)


# ── Prompt 2: Reconcile against DB skills (Stage 3) ──

def reconcile_skills(resume_text: str, db_skills_by_category: dict[str, list[str]]) -> dict:
    """Match resume against DB skill names. Returns {"matched": [...], "missing": [...]}."""
    prompt = RECONCILE_PROMPT.format(
        resume_text=resume_text,
        hard_skills=", ".join(db_skills_by_category.get("hard_skill", [])),
        soft_skills=", ".join(db_skills_by_category.get("soft_skill", [])),
        tools=", ".join(db_skills_by_category.get("tool", [])),
        certifications=", ".join(db_skills_by_category.get("certification", [])),
    )
    stdout = _call_claude(prompt)
    result = _parse_json(stdout)

    # Validate: matched + missing should cover all DB skills
    if "matched" not in result:
        result["matched"] = []
    if "missing" not in result:
        result["missing"] = []

    return result


# ── Prompt 3: Format JD (Stage 6.5) ──

def format_jd(description: str) -> str:
    """Reformat a raw job description into clean Markdown."""
    prompt = FORMAT_JD_PROMPT.format(description=description)
    stdout = _call_claude(prompt)
    return stdout.strip()


# ── Prompt 4: Gap Analysis + JD Highlight (Stage 7) ──

def generate_analysis(
    all_user_skills: list[str],
    noc_name: str,
    matched_skills: list[str],
    missing_skills: list[str],
    match_rate: float,
    company: str,
    title: str,
    description: str,
) -> dict:
    """Generate career analysis with strengths, gaps, recommendations, JD highlight."""
    prompt = ANALYSIS_PROMPT.format(
        all_user_skills=", ".join(all_user_skills),
        noc_name=noc_name,
        matched_skills=", ".join(matched_skills),
        missing_skills=", ".join(missing_skills),
        match_rate=f"{match_rate:.0%}",
        company=company,
        title=title,
        description=description,
    )
    stdout = _call_claude(prompt)
    return _parse_json(stdout)

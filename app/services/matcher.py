"""
Skill matching logic + DB queries.
SPEC: DB 쿼리 section — 3 queries for Sections 1-3.
"""


def calculate_match_rate(user_skills: list[str], required_skills: list[str]) -> dict:
    """Calculate skill match rate between user and required skills.

    Returns:
        {match_rate, matched, missing, total_required}
    """
    if not required_skills:
        return {"match_rate": 0.0, "matched": [], "missing": [], "total_required": 0}

    user_lower = {s.lower() for s in user_skills}
    req_lower = {s.lower() for s in required_skills}

    matched = sorted(user_lower & req_lower)
    missing = sorted(req_lower - user_lower)
    rate = len(matched) / len(req_lower) if req_lower else 0.0

    return {
        "match_rate": round(rate, 3),
        "matched": matched,
        "missing": missing,
        "total_required": len(req_lower),
    }


def get_noc_required_skills(conn, noc_code: str, seniority: str) -> list[dict]:
    """SPEC Query 1: Target NOC 요구 스킬."""
    cur = conn.cursor()
    cur.execute("""
        SELECT sk.name, sk.category, COUNT(*) as demand_count
        FROM fact_job_skill_demand f
        JOIN fact_job_postings p ON f.job_id = p.job_id
        JOIN dim_skills sk ON f.skill_id = sk.id
        JOIN dim_seniority ds ON p.seniority_id = ds.id
        WHERE p.noc_id = (SELECT id FROM noc_titles WHERE noc21_code = %s)
          AND ds.level = %s
        GROUP BY sk.name, sk.category
        ORDER BY demand_count DESC
        LIMIT 30
    """, (noc_code, seniority))
    rows = cur.fetchall()
    cur.close()
    return [{"name": r[0], "category": r[1], "demand_count": r[2]} for r in rows]


def find_similar_nocs(conn, user_skills: list[str]) -> list[dict]:
    """SPEC Query 2: 전체 NOC 유사도 (user skills 교집합)."""
    if not user_skills:
        return []

    placeholders = ",".join(["%s"] * len(user_skills))
    cur = conn.cursor()
    cur.execute(f"""
        SELECT n.noc21_code, n.noc21_name,
               COUNT(*) as overlap,
               COUNT(*) * 1.0 / NULLIF(total.cnt, 0) as match_rate
        FROM fact_job_skill_demand f
        JOIN fact_job_postings p ON f.job_id = p.job_id
        JOIN dim_skills sk ON f.skill_id = sk.id
        JOIN noc_titles n ON p.noc_id = n.id
        LEFT JOIN (
            SELECT p2.noc_id, COUNT(DISTINCT f2.skill_id) as cnt
            FROM fact_job_skill_demand f2
            JOIN fact_job_postings p2 ON f2.job_id = p2.job_id
            GROUP BY p2.noc_id
        ) total ON total.noc_id = p.noc_id
        WHERE sk.name IN ({placeholders})
        GROUP BY n.noc21_code, n.noc21_name, total.cnt
        ORDER BY match_rate DESC
        LIMIT 5
    """, user_skills)
    rows = cur.fetchall()
    cur.close()
    return [{"noc_code": r[0], "noc_name": r[1], "overlap": r[2], "match_rate": round(float(r[3]), 3) if r[3] else 0.0} for r in rows]


def find_best_posting(conn, noc_code: str, user_skills: list[str]) -> dict | None:
    """SPEC Query 3: 가장 유사한 job posting."""
    if not user_skills:
        return None

    placeholders = ",".join(["%s"] * len(user_skills))
    cur = conn.cursor()
    cur.execute(f"""
        SELECT p.job_id, c.name as company, p.raw_title, p.description,
               COUNT(*) as skill_overlap
        FROM fact_job_postings p
        JOIN dim_companies c ON p.company_id = c.id
        JOIN fact_job_skill_demand f ON f.job_id = p.job_id
        JOIN dim_skills sk ON f.skill_id = sk.id
        WHERE p.noc_id = (SELECT id FROM noc_titles WHERE noc21_code = %s)
          AND sk.name IN ({placeholders})
        GROUP BY p.job_id, c.name, p.raw_title, p.description
        ORDER BY skill_overlap DESC
        LIMIT 1
    """, [noc_code] + user_skills)
    row = cur.fetchone()
    cur.close()
    if not row:
        return None
    return {"company": row[1], "title": row[2], "description": row[3], "skill_overlap": row[4]}


def noc_exists(conn, noc_code: str) -> bool:
    """Check if NOC code exists in noc_titles."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM noc_titles WHERE noc21_code = %s", (noc_code,))
    exists = cur.fetchone() is not None
    cur.close()
    return exists


def get_noc_list(conn) -> list[dict]:
    """SPEC: GET /noc-list — all 510 NOC titles for Frontend dropdown."""
    cur = conn.cursor()
    cur.execute("SELECT noc21_code, noc21_name FROM noc_titles WHERE LENGTH(noc21_code) = 5 ORDER BY noc21_name")
    rows = cur.fetchall()
    cur.close()
    return [{"noc_code": r[0], "noc_name": r[1]} for r in rows]

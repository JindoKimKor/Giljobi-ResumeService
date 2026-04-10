"""
Neon DB connection manager.
SPEC: Two separate Neon DBs — market-trend (NOC titles) + skill-demand (star schema).
"""

import os
import psycopg2


def get_sd_connection():
    """Skill-demand DB (star schema: dim_skills, fact_job_skill_demand, etc.)."""
    url = os.environ.get("NEON_SD_DB_URL", "")
    if not url:
        raise RuntimeError("NEON_SD_DB_URL not set")
    return psycopg2.connect(url)


def get_mt_connection():
    """Market-trend DB (noc_titles)."""
    url = os.environ.get("NEON_MT_DB_URL", "")
    if not url:
        raise RuntimeError("NEON_MT_DB_URL not set")
    return psycopg2.connect(url)


def check_connection(conn) -> bool:
    """Verify DB connection is alive."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        return True
    except Exception:
        return False

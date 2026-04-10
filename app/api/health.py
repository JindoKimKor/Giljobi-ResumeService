"""
Health check + NOC list endpoints.
SPEC: GET /health, GET /noc-list
"""

from fastapi import APIRouter

from app.db.neon import get_sd_connection, get_mt_connection, check_connection
from app.services.matcher import get_noc_list

router = APIRouter()


@router.get("/health")
def health():
    """SPEC: GET /health → {status, db_mt, db_sd}"""
    status = {"status": "ok", "db_mt": "unknown", "db_sd": "unknown"}
    try:
        conn = get_mt_connection()
        status["db_mt"] = "connected" if check_connection(conn) else "error"
        conn.close()
    except Exception:
        status["db_mt"] = "error"

    try:
        conn = get_sd_connection()
        status["db_sd"] = "connected" if check_connection(conn) else "error"
        conn.close()
    except Exception:
        status["db_sd"] = "error"

    if "error" in (status["db_mt"], status["db_sd"]):
        status["status"] = "degraded"

    code = 200 if status["status"] == "ok" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=status, status_code=code)


@router.get("/noc-list")
def noc_list():
    """SPEC: GET /noc-list → [{noc_code, noc_name}, ...]"""
    conn = get_sd_connection()
    try:
        return get_noc_list(conn)
    finally:
        conn.close()

"""
WebSocket endpoint for resume analysis.
SPEC: /ws/analyze — 7-stage streaming.
"""

import json
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.validation import validate_input, ValidationError
from app.services.llm import extract_skills, generate_analysis, LLMError
from app.services.matcher import (
    get_noc_required_skills, calculate_match_rate,
    find_similar_nocs, find_best_posting, noc_exists,
)
from app.db.neon import get_sd_connection

router = APIRouter()


async def send_stage(ws: WebSocket, data: dict):
    """Send a stage message as JSON."""
    await ws.send_json(data)


async def send_error(ws: WebSocket, code: str, message: str):
    """Send error message and close WebSocket."""
    await ws.send_json({"stage": "error", "code": code, "message": message})
    await ws.close(code=1008 if code.startswith("INVALID") else 1011)


@router.websocket("/ws/analyze")
async def analyze_resume(ws: WebSocket):
    await ws.accept()

    try:
        # Receive input
        raw = await ws.receive_text()
        data = json.loads(raw)

        resume_text = data.get("resume_text", "")
        target_seniority = data.get("target_seniority", "")
        target_noc_code = data.get("target_noc_code", "")

        # Validate input
        try:
            validate_input(resume_text, target_seniority, target_noc_code)
        except ValidationError as e:
            await send_error(ws, e.code, e.message)
            return

        # DB connection
        try:
            conn = get_sd_connection()
        except Exception as e:
            await send_error(ws, "DB_ERROR", f"Failed to connect to Neon DB: {e}")
            return

        try:
            # Validate NOC exists in DB
            if not noc_exists(conn, target_noc_code):
                await send_error(ws, "INVALID_NOC", f"NOC code {target_noc_code} not found in database")
                return

            # ── Stage 1: Extract skills ──────────────────────────
            await send_stage(ws, {"stage": "extracting"})
            try:
                user_skills = extract_skills(resume_text)
            except LLMError as e:
                await send_error(ws, "LLM_FAILED", str(e))
                return
            await send_stage(ws, {"stage": "extracted", "skills": user_skills})

            # ── Stage 2: Match target NOC ────────────────────────
            await send_stage(ws, {"stage": "matching_noc"})
            required = get_noc_required_skills(conn, target_noc_code, target_seniority)
            required_names = [r["name"] for r in required]
            match_result = calculate_match_rate(user_skills, required_names)

            # Get NOC name
            cur = conn.cursor()
            cur.execute("SELECT noc21_name FROM noc_titles WHERE noc21_code = %s", (target_noc_code,))
            noc_name = cur.fetchone()[0]
            cur.close()

            await send_stage(ws, {
                "stage": "noc_match",
                "noc_code": target_noc_code,
                "noc_name": noc_name,
                "match_rate": match_result["match_rate"],
                "matched_skills": match_result["matched"],
                "missing_skills": match_result["missing"],
                "total_required": match_result["total_required"],
            })

            # ── Stage 3: Find similar NOCs ───────────────────────
            await send_stage(ws, {"stage": "finding_similar"})
            similar = find_similar_nocs(conn, user_skills)
            await send_stage(ws, {"stage": "similar_nocs", "top5": similar})

            # ── Stage 4: Find best posting ───────────────────────
            await send_stage(ws, {"stage": "finding_posting"})
            # Use the best matching NOC (could be target or top similar)
            best_noc = target_noc_code
            if similar and similar[0]["match_rate"] > match_result["match_rate"]:
                best_noc = similar[0]["noc_code"]
            posting = find_best_posting(conn, best_noc, user_skills)
            if posting:
                await send_stage(ws, {
                    "stage": "best_posting",
                    "company": posting["company"],
                    "title": posting["title"],
                    "description": posting["description"][:2000],
                    "skill_overlap": posting["skill_overlap"],
                    "match_rate": round(posting["skill_overlap"] / max(len(required_names), 1), 3),
                })
            else:
                await send_stage(ws, {
                    "stage": "best_posting",
                    "company": None,
                    "title": None,
                    "description": "No matching job posting found",
                    "skill_overlap": 0,
                    "match_rate": 0,
                })

            # ── Stage 5: Generate analysis ───────────────────────
            await send_stage(ws, {"stage": "analyzing"})
            try:
                analysis = generate_analysis(
                    user_skills=user_skills,
                    noc_name=noc_name,
                    noc_code=target_noc_code,
                    match_rate=match_result["match_rate"],
                    matched_skills=match_result["matched"],
                    missing_skills=match_result["missing"],
                    company=posting["company"] if posting else "N/A",
                    title=posting["title"] if posting else "N/A",
                    description=posting["description"][:2000] if posting else "No matching posting found",
                )
            except LLMError as e:
                await send_error(ws, "LLM_FAILED", str(e))
                return
            await send_stage(ws, {
                "stage": "analysis",
                "strengths": analysis.get("strengths", []),
                "gaps": analysis.get("gaps", []),
                "recommendations": analysis.get("recommendations", ""),
                "jd_highlighted": analysis.get("jd_highlighted", ""),
            })

            # ── Stage 6: Done ────────────────────────────────────
            await send_stage(ws, {"stage": "done"})

        finally:
            conn.close()

    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        await send_error(ws, "INVALID_INPUT", "Invalid JSON message")
    except Exception as e:
        try:
            await send_error(ws, "INTERNAL", f"Unexpected error: {e}")
        except Exception:
            pass

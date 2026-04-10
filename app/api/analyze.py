"""
WebSocket endpoint for resume analysis — 7-stage streaming.
SPEC: 처리 흐름 section.
"""

import base64
import io
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.validation import validate_input, ValidationError
from app.services.llm import extract_skills, reconcile_skills, generate_analysis, LLMError
from app.services.matcher import (
    get_noc_required_skills, group_skills_by_category, calculate_match_rate,
    find_similar_nocs, find_best_posting, noc_exists,
)
from app.db.neon import get_sd_connection

router = APIRouter()


async def send_stage(ws: WebSocket, data: dict):
    """Send a stage message as JSON."""
    print(f"[WS] → {data.get('stage', '?')}", flush=True)
    await ws.send_json(data)


async def send_error(ws: WebSocket, code: str, message: str):
    """Send error message and close WebSocket."""
    print(f"[WS] ERROR: {code} — {message}", flush=True)
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

        # PDF base64 → extract text with pypdf
        if resume_text.startswith("data:application/pdf;base64,"):
            try:
                from pypdf import PdfReader
                pdf_b64 = resume_text.split(",", 1)[1]
                pdf_bytes = base64.b64decode(pdf_b64)
                reader = PdfReader(io.BytesIO(pdf_bytes))
                resume_text = "\n".join(page.extract_text() or "" for page in reader.pages)
                print(f"[WS] PDF parsed: {len(resume_text)} chars", flush=True)
            except Exception as e:
                await send_error(ws, "INVALID_INPUT", f"Failed to parse PDF: {e}")
                return

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

            # Get NOC name
            cur = conn.cursor()
            cur.execute("SELECT noc21_name FROM noc_titles WHERE noc21_code = %s", (target_noc_code,))
            noc_name = cur.fetchone()[0]
            cur.close()

            # ── Stage 1: DB — NOC 스킬 조회 (category별 top 10) ──
            await send_stage(ws, {"stage": "loading_skills"})
            required = get_noc_required_skills(conn, target_noc_code, target_seniority)
            db_skills_by_cat = group_skills_by_category(required)
            all_db_skill_names = [s["name"] for s in required]

            print(f"[WS] DB skills: {len(all_db_skill_names)} total, categories: {list(db_skills_by_cat.keys())}", flush=True)
            for cat, names in db_skills_by_cat.items():
                print(f"[WS]   {cat}: {len(names)} — {names[:3]}...", flush=True)
            await send_stage(ws, {
                "stage": "noc_skills",
                "noc_name": noc_name,
                "skills_by_category": db_skills_by_cat,
                "total": len(all_db_skill_names),
            })

            # ── Stage 2: LLM #1 — 자유 스킬 추출 ──
            await send_stage(ws, {"stage": "extracting"})
            try:
                user_skills_free = extract_skills(resume_text)
            except LLMError as e:
                await send_error(ws, "LLM_FAILED", str(e))
                return
            print(f"[WS] Free extraction: {len(user_skills_free)} skills", flush=True)
            await send_stage(ws, {"stage": "extracted", "skills": user_skills_free})

            # ── Stage 3: LLM #2 — Reconcile (resume + DB 스킬 목록 대조) ──
            # LLM이 resume 맥락을 이해해서 "팀 리더 경험 → leadership" 같은 추론 가능
            # exact match로는 soft skills를 못 잡음
            await send_stage(ws, {"stage": "reconciling"})
            try:
                reconcile_result = reconcile_skills(resume_text, db_skills_by_cat)
            except LLMError as e:
                await send_error(ws, "LLM_FAILED", str(e))
                return
            matched_skills = reconcile_result.get("matched", [])
            missing_skills = reconcile_result.get("missing", [])
            print(f"[WS] Reconcile (LLM): {len(matched_skills)} matched, {len(missing_skills)} missing", flush=True)
            await send_stage(ws, {
                "stage": "reconciled",
                "matched": matched_skills,
                "missing": missing_skills,
            })

            # ── Stage 4: Match rate 계산 (category별) ──
            await send_stage(ws, {"stage": "matching_noc"})
            matched_set = set(s.lower() for s in matched_skills)

            # Category별 매치율 계산 (certification 제외)
            match_by_category = {}
            total_matched = 0
            total_required = 0
            for cat, skill_names in db_skills_by_cat.items():
                cat_matched = [s for s in skill_names if s.lower() in matched_set]
                cat_missing = [s for s in skill_names if s.lower() not in matched_set]
                cat_rate = len(cat_matched) / len(skill_names) if skill_names else 0.0
                match_by_category[cat] = {
                    "matched": cat_matched,
                    "missing": cat_missing,
                    "match_rate": round(cat_rate, 3),
                    "total": len(skill_names),
                }
                if cat != "certification":  # certification은 overall에서 제외
                    total_matched += len(cat_matched)
                    total_required += len(skill_names)

            match_rate = total_matched / total_required if total_required else 0.0

            await send_stage(ws, {
                "stage": "noc_match",
                "noc_code": target_noc_code,
                "noc_name": noc_name,
                "match_rate": round(match_rate, 3),
                "match_by_category": match_by_category,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "total_required": total_required,
            })

            # ── Stage 5: DB — Similar NOCs (same seniority, exclude target) ──
            await send_stage(ws, {"stage": "finding_similar"})
            similar = find_similar_nocs(conn, user_skills_free, target_seniority, target_noc_code)
            await send_stage(ws, {"stage": "similar_nocs", "top5": similar})

            # ── Stage 6: DB — Best posting (same NOC + seniority) ──
            await send_stage(ws, {"stage": "finding_posting"})
            posting = find_best_posting(conn, target_noc_code, target_seniority, user_skills_free)
            if posting:
                await send_stage(ws, {
                    "stage": "best_posting",
                    "company": posting["company"],
                    "title": posting["title"],
                    "description": posting["description"][:2000],
                    "skill_overlap": posting["skill_overlap"],
                })
            else:
                await send_stage(ws, {
                    "stage": "best_posting",
                    "company": None, "title": None,
                    "description": "No matching job posting found",
                    "skill_overlap": 0,
                })

            # ── Stage 7: LLM #3 — 종합 분석 ──
            await send_stage(ws, {"stage": "analyzing"})
            try:
                analysis = generate_analysis(
                    all_user_skills=user_skills_free,
                    noc_name=noc_name,
                    matched_skills=matched_skills,
                    missing_skills=missing_skills,
                    match_rate=match_rate,
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

            # ── Stage 8: Done ──
            await send_stage(ws, {"stage": "done"})

        finally:
            conn.close()

    except WebSocketDisconnect:
        pass
    except json.JSONDecodeError:
        try:
            await send_error(ws, "INVALID_INPUT", "Invalid JSON message")
        except Exception:
            pass
    except Exception as e:
        print(f"[WS] UNHANDLED: {e}", flush=True)
        try:
            await send_error(ws, "INTERNAL", f"Unexpected error: {e}")
        except Exception:
            pass

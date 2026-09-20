# Resume Analysis Service Specification

**Service:** GILJOBI Resume Analysis Service

**Framework:** FastAPI, WebSocket, Claude CLI, PostgreSQL/Neon

**Container target:** Azure Container Apps

**Verification status:** Updated against the current backend, frontend event handler, deployment files, and test suite on 2026-09-19.

## 1. Purpose

The service accepts a resume, a target seniority level, and a five-digit Canadian NOC code. It streams a skill and career analysis to the frontend while processing the request.

The analysis provides:

1. Required skills for the selected NOC and seniority.
2. Resume skills extracted by an LLM.
3. Matched and missing skills, including category-level match rates.
4. Up to five similar NOCs.
5. Up to three matching job postings.
6. Optional LLM-formatted job descriptions.
7. LLM-generated strengths, gaps, and recommendations.

## 2. Current Architecture

```text
Browser / GILJOBI Frontend
        |
        | WebSocket: /ws/analyze
        | HTTP: /health, /noc-list
        v
FastAPI Resume Service
        |-- Claude CLI subprocesses
        |-- Skill-demand Neon database
        `-- Market-trend Neon database (health check only)
```

### Responsibilities

| Component | Current responsibility |
|---|---|
| GILJOBI Frontend | Sends the resume request and renders streamed progress/results |
| FastAPI | Validates input, runs the workflow, queries Neon, and streams JSON events |
| Claude CLI | Extracts skills, reconciles DB skills, formats job descriptions, and generates analysis |
| Skill-demand DB | Supplies NOC titles, required skills, seniority, job postings, and skill demand data |
| Market-trend DB | Checked by `/health`; it is not used by the analysis workflow |

The FastAPI CORS configuration currently permits all origins. Authentication, authorization, rate limiting, and request persistence are not implemented.

## 3. API

### 3.1 WebSocket analysis

```text
WS  /ws/analyze
WSS /ws/analyze when deployed behind HTTPS
```

The server accepts the WebSocket, reads one JSON text message, processes it, and emits stage messages sequentially.

#### Input

```json
{
  "resume_text": "Experienced software engineer with five years of experience...",
  "target_seniority": "senior",
  "target_noc_code": "21231"
}
```

`resume_text` may also contain a PDF data URL:

```text
data:application/pdf;base64,<base64-data>
```

The service decodes the PDF and extracts text with `pypdf` before validation.

| Field | Validation |
|---|---|
| `resume_text` | 50 to 50,000 characters after PDF extraction |
| `target_seniority` | `intern`, `entry_level`, `mid_level`, `senior`, or `executive` |
| `target_noc_code` | Exactly five numeric characters and present in `noc_titles` |

Malformed JSON produces `INVALID_INPUT`.

### 3.2 Health check

```text
GET /health
```

The endpoint independently tests both Neon connections with `SELECT 1`.

```json
{
  "status": "ok",
  "db_mt": "connected",
  "db_sd": "connected"
}
```

- HTTP `200` is returned when both connections succeed.
- HTTP `503` with `status: "degraded"` is returned when either connection fails.

### 3.3 NOC list

```text
GET /noc-list
```

The endpoint reads five-digit NOC codes from the skill-demand database and returns:

```json
[
  {
    "noc_code": "21231",
    "noc_name": "Software engineers and designers"
  }
]
```

The result is ordered by NOC name. The implementation does not enforce or test a fixed count such as 510.

## 4. WebSocket Workflow

The implementation has eight logical processing stages and emits both progress and result events. The number of JSON messages varies because job-description formatting is skipped when no postings are found.

### Stage 1: Load NOC skills

Events:

```json
{"stage": "loading_skills"}
{"stage": "noc_skills", "noc_name": "...", "skills_by_category": {}, "total": 0}
```

Behavior:

- Connects to the skill-demand database.
- Confirms that the selected NOC exists.
- Selects the top 15 skills per category for the selected NOC and seniority.
- Groups skill names by category for the reconciliation prompt.

### Stage 2: Extract resume skills

Events:

```json
{"stage": "extracting"}
{"stage": "extracted", "skills": ["python", "aws", "docker"]}
```

Claude receives the resume text and returns a JSON array of freely extracted skills. The current implementation does not apply `inflect` normalization or any other post-processing.

### Stage 3: Reconcile against database skills

Events:

```json
{"stage": "reconciling"}
{"stage": "reconciled", "matched": ["python"], "missing": ["kubernetes"]}
```

Claude receives the resume and the categorized database skill names. The prompt instructs Claude to return only exact names from the supplied lists.

The code supplies missing `matched` or `missing` keys with empty arrays, but it does not verify that the two arrays are disjoint or that their union contains every database skill. Therefore, complete coverage is requested by the prompt but not programmatically guaranteed.

### Stage 4: Calculate the target-NOC match

Events:

```json
{"stage": "matching_noc"}
{
  "stage": "noc_match",
  "noc_code": "21231",
  "noc_name": "Software engineers and designers",
  "match_rate": 0.78,
  "match_by_category": {},
  "matched_skills": ["python"],
  "missing_skills": ["kubernetes"],
  "total_required": 15
}
```

Category matching is case-insensitive. Certifications appear in `match_by_category` but are excluded from the overall match rate and `total_required`.

### Stage 5: Find similar NOCs

Events:

```json
{"stage": "finding_similar"}
{"stage": "similar_nocs", "top5": []}
```

The query:

- Uses freely extracted resume skills.
- Filters postings to the selected seniority.
- Excludes the target NOC.
- Ranks NOCs by matched-skill count divided by the total distinct demanded skills for that NOC and seniority.
- Returns at most five results.

### Stage 6: Find matching postings

Events:

```json
{"stage": "finding_posting"}
{
  "stage": "best_postings",
  "postings": [
    {
      "company": "Example Company",
      "title": "Senior Software Engineer",
      "description": "...",
      "skill_overlap": 8
    }
  ]
}
```

The query searches postings with the selected NOC and seniority, ranks them by overlap with freely extracted skills, and returns at most three. Each description is truncated to 2,000 characters before being sent to the frontend.

The event is `best_postings` and contains a list. There is no posting-level `match_rate` field.

### Stage 7: Optionally format job descriptions

These events are emitted only when at least one posting exists:

```json
{"stage": "formatting_jd"}
{"stage": "formatted_jd", "formatted_jds": ["..."]}
```

Claude is invoked separately for each returned posting. A formatting failure is non-fatal: the service inserts an empty string for that posting and continues.

### Stage 8: Generate career analysis and finish

Events:

```json
{"stage": "analyzing"}
{
  "stage": "analysis",
  "strengths": [],
  "gaps": [],
  "recommendations": "..."
}
{"stage": "done"}
```

The analysis prompt requests `strengths`, `gaps`, `recommendations`, and `jd_highlighted`. The current WebSocket handler sends only the first three fields; `jd_highlighted` is currently discarded.

## 5. Claude CLI Behavior

Every call runs:

```text
claude --print --model haiku -
```

The prompt is sent through standard input. `CLAUDE_HOME`, when set, is used as the subprocess `HOME`; otherwise the operating-system home directory is used.

The service performs:

| Call | Required? | Purpose |
|---|---|---|
| Skill extraction | Yes | Extract free-form resume skills |
| Skill reconciliation | Yes | Match the resume to exact database skill names |
| JD formatting | Once per posting | Reformat zero to three posting descriptions |
| Career analysis | Yes | Generate strengths, gaps, and recommendations |

Consequently, a successful request makes between three and six Claude calls.

JSON responses are extracted using a greedy regular expression from the first `[` or `{` through the last `]` or `}` and then parsed with `json.loads`.

## 6. Database Behavior

### Skill-demand connection

`NEON_SD_DB_URL` is required for:

- `/ws/analyze`
- `/noc-list`
- The skill-demand portion of `/health`

The analysis uses these tables:

- `noc_titles`
- `fact_job_skill_demand`
- `fact_job_postings`
- `dim_skills`
- `dim_seniority`
- `dim_companies`

All user values are passed as SQL parameters. The dynamic `IN` lists are constructed from `%s` placeholders, not from raw skill values.

### Market-trend connection

`NEON_MT_DB_URL` is used only by `/health` in the current implementation.

### Connection lifetime

The analysis creates one skill-demand connection per WebSocket request and closes it in a `finally` block. There is no connection pool.

## 7. Error Handling

```json
{"stage": "error", "code": "INVALID_INPUT", "message": "..."}
```

After sending an error event, the service closes the WebSocket:

| Code | Current cause | Close code |
|---|---|---|
| `INVALID_INPUT` | Invalid JSON, PDF parsing failure, or invalid resume length | `1008` when sent through `send_error` |
| `INVALID_SENIORITY` | Unsupported seniority | `1008` |
| `INVALID_NOC` | Invalid NOC format or NOC absent from the database | `1008` |
| `LLM_FAILED` | Claude process failure or invalid JSON response | `1011` |
| `DB_ERROR` | Initial skill-demand connection failure | `1011` |
| `INTERNAL` | Unhandled errors, including database query errors after connection | `1011` |

Completed events remain visible to the frontend after an error, but the backend does not support resuming at the failed stage. A retry starts a new WebSocket request from the beginning.

## 8. Frontend Compatibility

The current GILJOBI frontend handler recognizes all backend event names:

```text
loading_skills, noc_skills,
extracting, extracted,
reconciling, reconciled,
matching_noc, noc_match,
finding_similar, similar_nocs,
finding_posting, best_postings,
formatting_jd, formatted_jd,
analyzing, analysis,
done, error
```

The frontend progressively updates status and stores intermediate results. It opens the results view after receiving `done`.

## 9. Runtime and Deployment

### Required environment variables

| Variable | Required by | Description |
|---|---|---|
| `NEON_SD_DB_URL` | Analysis, NOC list, health | Skill-demand PostgreSQL connection string |
| `NEON_MT_DB_URL` | Health | Market-trend PostgreSQL connection string |
| `CLAUDE_HOME` | Optional | Claude CLI home/credential directory used by the subprocess |

Connection strings and credentials must be supplied at runtime and must not be committed.

### Local Python

```bash
pip install -r requirements.txt
export NEON_SD_DB_URL='...'
export NEON_MT_DB_URL='...'
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Local Docker helper

`run-local.sh` requires both database URLs in the caller's environment. It mounts `${CLAUDE_DIR:-$HOME/.claude}` into `/root/.claude`.

```bash
export NEON_SD_DB_URL='...'
export NEON_MT_DB_URL='...'
./run-local.sh
```

### Production container

The tracked `Dockerfile` installs Python 3.12, Node.js 20, Claude Code, and the Python dependencies. It does not copy credentials into the image. Uvicorn runs on port 8000 with a 60-second WebSocket ping interval and a 120-second timeout.

Local working-tree deployment assets currently include `Dockerfile.deploy`, `deploy.sh`, and `infra/terraform/`. They are not tracked at the time of this verification. `Dockerfile.deploy` copies `.claude` credentials into the image, which is inappropriate for a durable production image; a managed secret or runtime identity should replace this approach before production use.

## 10. Project Structure

```text
Giljobi-ResumeService/
├── app/
│   ├── api/
│   │   ├── analyze.py
│   │   └── health.py
│   ├── db/
│   │   └── neon.py
│   ├── services/
│   │   ├── llm.py
│   │   ├── matcher.py
│   │   └── validation.py
│   └── main.py
├── tests/
│   ├── test_llm.py
│   ├── test_matcher.py
│   └── test_validation.py
├── Dockerfile
├── requirements.txt
├── run-local.sh
└── SPEC.md
```

PDF extraction is implemented directly in `app/api/analyze.py`; there is no separate `resume.py` module.

## 11. Automated Tests

The tracked suite currently contains 30 unit tests:

- `test_validation.py`: resume length, seniority, and NOC-format validation.
- `test_matcher.py`: pure `calculate_match_rate` behavior.
- `test_llm.py`: mocked Claude subprocess behavior for extraction, reconciliation, parsing, and analysis.

Verified result on 2026-09-19:

```text
30 passed
```

The repository does not currently contain automated database integration tests, endpoint tests, WebSocket tests, PDF tests, JD-formatting tests, or end-to-end tests.

## 12. Known Gaps and Risks

1. The reconciliation result is not checked for complete or valid database-skill coverage.
2. `jd_highlighted` is requested from Claude but omitted from the WebSocket response.
3. Database query failures after connection are reported as `INTERNAL`, not `DB_ERROR`.
4. There is no authentication, authorization, rate limiting, or connection pooling.
5. CORS currently allows every origin while also allowing credentials.
6. Claude prompts include resume and job-description content; privacy and retention requirements must be reviewed before production use.
7. The JSON extractor is greedy and may fail if Claude emits multiple JSON structures.
8. JD formatting makes one sequential Claude call per posting, increasing latency.
9. Deployment credentials should be injected at runtime rather than baked into an image.
10. Integration and end-to-end coverage are still missing.

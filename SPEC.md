# Resume Analysis Service Specification

**Purpose:** Real-time resume analysis against job market data — skill matching, NOC recommendations, gap analysis.
**Platform:** Azure Container Apps (scale to 0, HTTPS 자동)
**Framework:** FastAPI + Claude CLI (WebSocket)
**Repo:** `Giljobi-ResumeService` (독립 — DataPipeline과 분리)

---

## Architecture

```
┌─────────────┐         ┌────────────────────────────────────┐     ┌──────────┐
│   Vercel    │   WS    │  Azure Container Apps              │     │ Neon DB  │
│  (Frontend) │────────▶│  Resume Service                    │────▶│ (Shared) │
│             │   wss://│  FastAPI + Claude CLI               │     │ market-  │
└─────────────┘         │  scale: 0 (idle) → 1+ (demo)      │     │ trend +  │
                        │  2 vCPU, 4GB RAM per replica       │     │ skill-   │
                        └────────────────────────────────────┘     │ demand   │
                                                                   └──────────┘
```

### Platform

| 항목 | 결정 |
|------|------|
| Platform | **Azure Container Apps** (scale to 0, HTTPS 자동) |
| Framework | FastAPI + Claude CLI |
| 통신 | WebSocket (단계별 스트리밍) |
| 연결 | Frontend (Vercel) ↔ ACA (wss://) ↔ Neon DB (양쪽) + Claude CLI |
| Replicas | idle: 0 (비용 $0), demo: 1+ (2 vCPU, 4GB per replica) |
| Docker | `Dockerfile` → ACR or Docker Hub → ACA |

### Why Azure Container Apps (not VM / App Service)

| | VM (같은 곳) | App Service | Container Apps |
|--|-------------|-------------|----------------|
| Scale to 0 | ❌ | ❌ (최소 1) | ✅ 진짜 0 |
| Idle 비용 | VM 비용 포함 | ~$13/mo | **$0** |
| HTTPS | Nginx+Let's Encrypt 직접 | 자동 | 자동 |
| WebSocket | 직접 설정 | ✅ | ✅ |
| 독립 lifecycle | VM 재시작 시 같이 죽음 | ✅ | ✅ |
| vCPU quota | VM 6 vCPU 공유 | 별도 plan | **별도 quota** |

### Why separate repo (not DataPipeline)

- **다른 lifecycle** — DataPipeline은 batch(가끔 실행), Resume Service는 실시간(항상 대기)
- **다른 배포 대상** — DataPipeline → VM Docker Compose, Resume Service → ACA
- **다른 의존성** — DataPipeline은 Airflow/Spark/Livy, Resume Service는 FastAPI/Claude CLI
- **독립 CI/CD** — 각 repo가 자기 Docker image를 빌드/푸시

---

## Use Case

사용자가 Resume를 업로드하고 target seniority + NOC title을 선택하면, 시장 데이터 기반으로 매칭 분석을 제공.

### 사용자 입력

```
1. Resume (PDF or text) — drag & drop
2. Target seniority — 드롭다운 (intern / entry / mid / senior / executive)
3. Target NOC title — 검색 드롭다운 (510개 중 선택)
```

### 결과 구성 (4 sections)

#### Section 1: Target NOC 매치율

```
"Software engineers and designers" — 78% match (12/15 skills)

✅ 보유 스킬:        python, java, sql, aws, docker, git, rest api, ...
❌ 부족 스킬:        kubernetes, terraform, ci/cd
```

**데이터 소스:** `dim_skills` + `fact_job_skill_demand`
**LLM 역할:** Resume에서 스킬 추출

#### Section 2: 다른 NOC 유사도 TOP 5

```
1. Data scientists (21211)              — 71% match
2. Web developers and programmers (21234) — 68% match
3. Database analysts (21223)             — 65% match
```

**데이터 소스:** 전체 NOC 스킬 교집합 비율
**LLM 역할:** 없음 (DB 쿼리 + 계산)

#### Section 3: 가장 유사한 실제 Job Posting

```
🏢 Google — Senior Software Engineer

Job Description:
"We are looking for a Senior Software Engineer with experience in
 [✅ Python], [✅ distributed systems], and [❌ Kubernetes]..."

매치율: 85%
```

**데이터 소스:** `fact_job_postings` (스킬 overlap 최대)
**LLM 역할:** JD 하이라이트 마킹

#### Section 4: 강점 & Gap 분석

```
💪 강점: Backend 스택 일치율 높음 (Python, Java, SQL)
📋 Gap: Kubernetes (82% 요구), CI/CD (74%), 경력 5+ years
🎯 추천: Kubernetes 학습 우선, Data Scientist 방향도 유리
```

**LLM 역할:** 종합 분석 텍스트 생성

---

## Frontend UX Flow — 화면 레이아웃

### Screen 1: Input Form

```
┌─────────────────────────────────────────────────────────────┐
│  GILJOBI              Market Insights | Skill Demand | Resume│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │                                                     │   │
│   │         📄 Drop your resume here                    │   │
│   │            or click to browse                       │   │
│   │                                                     │   │
│   │         Supports PDF, TXT                           │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   Target Seniority:                                         │
│   ┌──────────────────────────────────────────────┐          │
│   │  [All ▼]  Entry | Mid | Senior | Executive   │          │
│   └──────────────────────────────────────────────┘          │
│                                                             │
│   Target Occupation (NOC):                                  │
│   ┌──────────────────────────────────────────────┐          │
│   │  🔍 Search... (e.g. "Software engineers")     │          │
│   │  ┌──────────────────────────────────────────┐ │          │
│   │  │ Software engineers and designers (21231) │ │          │
│   │  │ Software developers and programmers      │ │          │
│   │  │ Web developers and programmers           │ │          │
│   │  └──────────────────────────────────────────┘ │          │
│   └──────────────────────────────────────────────┘          │
│                                                             │
│            [ 🔍 Analyze My Resume ]                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Screen 2: Progress (WebSocket streaming)

각 stage 완료 시 해당 행에 ✅ 체크 + 결과 요약이 나타남. 아직 안 된 stage는 회색.

```
┌─────────────────────────────────────────────────────────────┐
│  GILJOBI              Market Insights | Skill Demand | Resume│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Analyzing resume for: Software engineers and designers    │
│   Seniority: Senior                                         │
│                                                             │
│   ✅ Extracting skills ─────────────── 12 skills found      │
│      python, aws, docker, sql, java, git, rest api,         │
│      spring boot, postgresql, linux, ci/cd, agile           │
│                                                             │
│   ✅ Matching target NOC ──────────── 78% match (12/15)     │
│   ⏳ Finding similar occupations...                          │
│   ○  Finding best job posting                                │
│   ○  Generating career analysis                              │
│                                                             │
│   ┌─ Progress ──────────────────────────────────────────┐   │
│   │ ████████████████████░░░░░░░░░░░░░░░░░░░░  3/5       │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Stage indicator states:
- `✅` — 완료 (결과 요약 표시)
- `⏳` — 진행 중 (스피너 애니메이션)
- `○` — 대기 (회색)

### Screen 3: Results (전체 완료 후)

4개 section 카드가 순서대로 나타남. 각 section은 WebSocket stage 완료 시 즉시 렌더 (전체 완료 기다리지 않음).

```
┌─────────────────────────────────────────────────────────────┐
│  GILJOBI              Market Insights | Skill Demand | Resume│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   📄 Resume Analysis — Software engineers and designers     │
│   Seniority: Senior | 12 skills extracted                   │
│                                                             │
│   ┌─ Section 1: Target NOC Match ───────────────────────┐   │
│   │                                                     │   │
│   │  Software engineers and designers    78% match      │   │
│   │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 12 / 15       │   │
│   │                                                     │   │
│   │  ✅ Matched:                                        │   │
│   │  [python] [sql] [aws] [docker] [java] [git]         │   │
│   │  [rest api] [spring boot] [postgresql] [linux]       │   │
│   │  [ci/cd] [agile]                                    │   │
│   │                                                     │   │
│   │  ❌ Missing:                                        │   │
│   │  [kubernetes] [terraform] [microservices]            │   │
│   │                                                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ┌─ Section 2: Similar Occupations ────────────────────┐   │
│   │                                                     │   │
│   │  1. Data scientists ───────────────── 71%  (8/11)   │   │
│   │  2. Web developers and programmers ── 68%  (7/10)   │   │
│   │  3. Database analysts ─────────────── 65%  (6/9)    │   │
│   │  4. Computer systems developers ───── 62%  (5/8)    │   │
│   │  5. Information systems specialists ─ 58%  (5/9)    │   │
│   │                                                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ┌─ Section 3: Best Matching Job Posting ──────────────┐   │
│   │                                                     │   │
│   │  🏢 Google — Senior Software Engineer    85% match   │   │
│   │                                                     │   │
│   │  "We are looking for a Senior Software Engineer     │   │
│   │   with experience in [✅ Python],                    │   │
│   │   [✅ distributed systems], and [❌ Kubernetes].      │   │
│   │   The ideal candidate has [❌ 5+ years experience]   │   │
│   │   in building [✅ cloud-native applications] with    │   │
│   │   [✅ AWS] or GCP..."                                │   │
│   │                                                     │   │
│   │  ✅ = your skill matches    ❌ = gap                 │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│   ┌─ Section 4: Career Analysis ────────────────────────┐   │
│   │                                                     │   │
│   │  💪 Strengths:                                      │   │
│   │  • Backend stack matches market demand               │   │
│   │    (Python, Java, SQL)                               │   │
│   │  • Cloud experience (AWS, Docker) — 78% of           │   │
│   │    SWE JDs require this                              │   │
│   │  • REST API design — senior level core skill         │   │
│   │                                                     │   │
│   │  📋 Skill Gaps:                                     │   │
│   │  • Kubernetes ── 82% require ─── ██████████ highest  │   │
│   │  • CI/CD ─────── 74% require ─── ████████           │   │
│   │  • Terraform ─── 45% require ─── █████              │   │
│   │                                                     │   │
│   │  🎯 Recommendations:                                │   │
│   │  Focus on Kubernetes (top missing skill). Data       │   │
│   │  Scientist (71% match) is also viable with current   │   │
│   │  skillset.                                           │   │
│   │                                                     │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│            [ 📄 Upload New Resume ]                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Screen 4: Error

```
┌─────────────────────────────────────────────────────────────┐
│  GILJOBI              Market Insights | Skill Demand | Resume│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ✅ Extracting skills ─────────────── 12 skills found      │
│   ✅ Matching target NOC ──────────── 78% match             │
│   ❌ Finding similar occupations ──── Error                  │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │  ⚠️  Analysis could not be completed                │   │
│   │                                                     │   │
│   │  Error: Failed to connect to database               │   │
│   │  Code: DB_ERROR                                     │   │
│   │                                                     │   │
│   │  Partial results are shown above.                   │   │
│   │                                                     │   │
│   │       [ 🔄 Retry ]    [ 📄 New Resume ]              │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### WebSocket Stage → UI Mapping

| WS Stage | Progress Indicator | UI Action |
|----------|-------------------|-----------|
| `extracting` | ⏳ "Extracting skills..." | 스피너 시작 |
| `extracted` | ✅ "12 skills found" | 스킬 칩/뱃지 표시, progress 1/5 |
| `matching_noc` | ⏳ "Matching target NOC..." | |
| `noc_match` | ✅ "78% match (12/15)" | **Section 1 카드 렌더** (즉시), progress 2/5 |
| `finding_similar` | ⏳ "Finding similar occupations..." | |
| `similar_nocs` | ✅ "5 similar found" | **Section 2 카드 렌더** (즉시), progress 3/5 |
| `finding_posting` | ⏳ "Finding best job posting..." | |
| `best_posting` | ✅ "Google — Senior SWE" | **Section 3 카드 렌더** (즉시), progress 4/5 |
| `analyzing` | ⏳ "Generating career analysis..." | |
| `analysis` | ✅ "Analysis complete" | **Section 4 카드 렌더** (즉시), progress 5/5 |
| `done` | 전체 완료 | progress bar 100%, "Upload New Resume" 버튼 표시 |
| `error` | ❌ 에러 발생 시점 | 에러 메시지 + Retry 버튼, 완료된 section은 유지 |

### Key UX Decisions

- **Progressive rendering** — 각 section은 해당 stage 완료 즉시 나타남 (done 기다리지 않음). 사용자가 30초 빈 화면을 보지 않음
- **Partial results on error** — 에러 발생 전까지 완료된 section은 유지. Retry 시 실패한 stage부터 재시작
- **Skill chips** — matched(초록) vs missing(빨강) 색상 구분
- **JD highlight** — `[✅ Python]` `[❌ Kubernetes]` 인라인 마크업 → Frontend에서 색상 badge로 렌더
- **Gap bar chart** — Section 4의 skill gap을 수평 bar로 시각화 (demand % 기준)

---

## 처리 흐름 (WebSocket 단계별 스트리밍)

```
Frontend                          Resume Service (ACA)
   │                                     │
   ├─ WS connect ──────────────────────▶ │
   ├─ send: {resume, seniority, noc} ──▶ │
   │                                     │
   │  ◀── {"stage": "loading_skills"}    ├─ 1. DB: target NOC 스킬 조회 (category별 top 10)
   │  ◀── {"stage": "noc_skills", ...}   │
   │                                     │
   │  ◀── {"stage": "extracting"}        ├─ 2. LLM #1: resume → 자유 스킬 추출
   │  ◀── {"stage": "extracted", ...}    │     + inflect 단수화 (DataPipeline과 동일)
   │                                     │
   │  ◀── {"stage": "reconciling"}       ├─ 3. LLM #2: resume + DB 스킬 목록 → reconcile
   │  ◀── {"stage": "reconciled", ...}   │     "이 목록 중 보유한 것을 골라줘"
   │                                     │
   │  ◀── {"stage": "matching_noc"}      ├─ 4. Match rate 계산 (DB 이름 기준 exact match)
   │  ◀── {"stage": "noc_match", ...}    │
   │                                     │
   │  ◀── {"stage": "finding_similar"}   ├─ 5. DB: 전체 NOC 유사도
   │  ◀── {"stage": "similar_nocs", ...} │
   │                                     │
   │  ◀── {"stage": "finding_posting"}   ├─ 6. DB: 가장 유사한 job posting
   │  ◀── {"stage": "best_posting", ...} │
   │                                     │
   │  ◀── {"stage": "analyzing"}         ├─ 7. LLM #3: 종합 분석 + JD 하이라이트
   │  ◀── {"stage": "analysis", ...}     │
   │                                     │
   │  ◀── {"stage": "done"}              │
   └─ WS close ─────────────────────────┘
```

### Stage Detail

**Stage 1 — DB: NOC 스킬 조회**
- target NOC + seniority로 DB 쿼리
- category별 top 10 (hard_skill 10, soft_skill 10, tool 10, certification 10)
- 이 목록이 Stage 3 reconcile의 기준이 됨

**Stage 2 — LLM #1: 자유 스킬 추출**
- resume 텍스트만 주고 자유롭게 추출
- inflect 단수화 적용 (DataPipeline `step4_load.py`의 `normalize_skills()`와 동일)
- 결과: user의 전체 스킬 목록 (DB 이름과 무관)

**Stage 3 — LLM #2: Reconcile (DB 스킬 목록과 대조)**
- resume + DB 스킬 목록(Stage 1)을 같이 주고
- "이 목록의 스킬 중에서 이 resume에 해당하는 것을 정확히 골라줘"
- LLM이 DB에 있는 이름 그대로 반환 → exact match 보장
- 결과: matched_skills (DB 이름), missing_skills (DB 이름)

**Stage 4 — Match rate 계산**
- Stage 3의 matched/missing로 비율 계산
- DB 이름 기준이라 불일치 없음

**Stage 5~6 — DB 쿼리** (기존과 동일)

**Stage 7 — LLM #3: 종합 분석**
- Stage 2(자유 추출) + Stage 3(reconcile 결과) + Stage 6(best posting)을 context로
- strengths, gaps, recommendations, jd_highlighted 생성

---

## API

### WebSocket Endpoint

```
wss://<aca-url>/ws/analyze
```

### Input Message (client → server)

```json
{
  "resume_text": "Experienced software engineer with 5 years...",
  "target_seniority": "senior",
  "target_noc_code": "21231"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `resume_text` | string | ✅ | min 50 chars, max 50,000 chars |
| `target_seniority` | string | ✅ | one of: `intern`, `entry_level`, `mid_level`, `senior`, `executive` |
| `target_noc_code` | string | ✅ | 5-digit NOC code, must exist in `noc_titles` table |

### Output Messages (server → client) — 7 stages

Each message is a JSON object with `stage` field. Sent sequentially via WebSocket.

**Stage 1: extracting → extracted**
```json
{"stage": "extracting"}
{"stage": "extracted", "skills": ["python", "aws", "docker", "sql", "rest api", "git"]}
```

**Stage 2: matching_noc**
```json
{"stage": "matching_noc"}
{"stage": "noc_match", "noc_code": "21231", "noc_name": "Software engineers and designers", "match_rate": 0.78, "matched_skills": ["python", "sql", "aws", "docker"], "missing_skills": ["kubernetes", "terraform", "ci/cd"], "total_required": 15}
```

**Stage 3: finding_similar**
```json
{"stage": "finding_similar"}
{"stage": "similar_nocs", "top5": [
  {"noc_code": "21211", "noc_name": "Data scientists", "match_rate": 0.71, "overlap": 8},
  {"noc_code": "21234", "noc_name": "Web developers and programmers", "match_rate": 0.68, "overlap": 7},
  {"noc_code": "21223", "noc_name": "Database analysts and data administrators", "match_rate": 0.65, "overlap": 6},
  {"noc_code": "21230", "noc_name": "Computer systems developers and programmers", "match_rate": 0.62, "overlap": 5},
  {"noc_code": "21222", "noc_name": "Information systems specialists", "match_rate": 0.58, "overlap": 5}
]}
```

**Stage 4: finding_posting**
```json
{"stage": "finding_posting"}
{"stage": "best_posting", "company": "Google", "title": "Senior Software Engineer", "description": "We are looking for...", "skill_overlap": 12, "match_rate": 0.85}
```

**Stage 5: analyzing**
```json
{"stage": "analyzing"}
{"stage": "analysis", "strengths": ["Backend stack matches market demand (Python, Java, SQL)", "Cloud experience (AWS, Docker) — 78% of SWE JDs require this"], "gaps": ["Kubernetes — 82% of Senior SWE JDs require, highest priority", "CI/CD — 74% require", "Terraform — 45% require, growing trend"], "recommendations": "Focus on Kubernetes (top missing skill). Data Scientist (71% match) is also viable with current skillset.", "jd_highlighted": "We are looking for a Senior Software Engineer with experience in [✅ Python], [✅ distributed systems], and [❌ Kubernetes]. The ideal candidate has [❌ 5+ years experience] in building [✅ cloud-native applications] with [✅ AWS] or GCP..."}
```

**Stage 6: done**
```json
{"stage": "done"}
```

### Error Messages

에러 발생 시 `stage: "error"` 메시지를 보내고 WebSocket을 닫음.

```json
{"stage": "error", "code": "INVALID_INPUT", "message": "resume_text must be at least 50 characters"}
{"stage": "error", "code": "INVALID_SENIORITY", "message": "target_seniority must be one of: intern, entry_level, mid_level, senior, executive"}
{"stage": "error", "code": "INVALID_NOC", "message": "NOC code 99999 not found in database"}
{"stage": "error", "code": "LLM_FAILED", "message": "Claude CLI returned non-zero exit code"}
{"stage": "error", "code": "DB_ERROR", "message": "Failed to connect to Neon DB"}
{"stage": "error", "code": "INTERNAL", "message": "Unexpected error during analysis"}
```

| Error Code | When | HTTP Close Code |
|------------|------|-----------------|
| `INVALID_INPUT` | resume_text too short/long | 1008 (Policy Violation) |
| `INVALID_SENIORITY` | seniority not in allowed set | 1008 |
| `INVALID_NOC` | noc_code not in DB | 1008 |
| `LLM_FAILED` | Claude CLI subprocess error | 1011 (Internal Error) |
| `DB_ERROR` | Neon DB connection/query failure | 1011 |
| `INTERNAL` | Unhandled exception | 1011 |

### Health Check

```
GET /health
→ 200 {"status": "ok", "db_mt": "connected", "db_sd": "connected"}
→ 503 {"status": "degraded", "db_mt": "error", "db_sd": "connected"}
```

### NOC List (for Frontend dropdown)

```
GET /noc-list
→ 200 [
  {"noc_code": "21231", "noc_name": "Software engineers and designers"},
  {"noc_code": "21232", "noc_name": "Software developers and programmers"},
  ...
]
```

---

## Input Validation

| Check | When | Error |
|-------|------|-------|
| `resume_text` length 50~50,000 | WebSocket message received | `INVALID_INPUT` |
| `target_seniority` in allowed set | WebSocket message received | `INVALID_SENIORITY` |
| `target_noc_code` exists in `noc_titles` | Before Stage 2 (DB lookup) | `INVALID_NOC` |
| Claude CLI exit code == 0 | After each LLM call | `LLM_FAILED` |
| LLM response is valid JSON | After each LLM call | `LLM_FAILED` |
| DB query returns rows | After each query | `DB_ERROR` (or empty result → skip section) |

---

## LLM Prompts (3 calls)

### Prompt 1: Free Skill Extraction (Stage 2)

```
Extract all technical skills, tools, and certifications from this resume.
Return ONLY a JSON array of lowercase strings. No explanation.

Example output: ["python", "aws", "docker", "sql", "kubernetes", "ci/cd"]

Resume:
{resume_text}
```

**Expected output:** `["python", "aws", "docker", ...]`
**Parse:** `json.loads(stdout)` → `List[str]`
**Post-process:** inflect 단수화 (DataPipeline과 동일 — "kubernetes"→"kubernete" 같은 건 KEEP_PLURAL로 보호)
**Failure mode:** If not valid JSON array → `LLM_FAILED`

### Prompt 2: Reconcile against DB skills (Stage 3)

```
Given a resume and a list of skills from a job category database, identify which skills the candidate has.

IMPORTANT: Return ONLY skills from the provided list. Use the EXACT names from the list.
Do not add skills that are not in the list. Do not modify skill names.

Skills list (from database):
Hard Skills: {hard_skills}
Soft Skills: {soft_skills}
Tools: {tools}
Certifications: {certifications}

Return a JSON object with matched and missing skills:
{
  "matched": ["skill1", "skill2", ...],
  "missing": ["skill3", "skill4", ...]
}

Resume:
{resume_text}
```

**Expected output:** `{"matched": [...], "missing": [...]}`
**Parse:** `json.loads(stdout)` → `dict`
**Key guarantee:** matched + missing = 전체 DB 스킬 목록 (빠짐없이)
**Failure mode:** If not valid JSON → `LLM_FAILED`

### Prompt 3: Gap Analysis + JD Highlight (Stage 7)

```
You are a career analyst. Given a candidate's skills, their match against a target job category, and a real job posting, provide:

1. strengths: List of 2-4 bullet points about the candidate's strong areas relative to market demand
2. gaps: List of 2-4 specific skill gaps with market demand percentage (e.g. "Kubernetes — 82% of JDs require")
3. recommendations: 1-2 sentences of actionable advice
4. jd_highlighted: The job description with matched skills marked as [✅ skill] and missing skills as [❌ skill]

Return as JSON:
{
  "strengths": ["..."],
  "gaps": ["..."],
  "recommendations": "...",
  "jd_highlighted": "..."
}

Candidate's extracted skills (free extraction): {all_user_skills}
Matched against DB ({noc_name}): {matched_skills}
Missing from DB: {missing_skills}
Match rate: {match_rate}

Best matching job posting:
Company: {company}
Title: {title}
Description:
{description}
```

**Expected output:** JSON with 4 fields
**Parse:** `json.loads(stdout)` → `dict`
**Failure mode:** If not valid JSON → `LLM_FAILED`

### Claude CLI Invocation

```python
result = subprocess.run(
    ["claude", "--print", "--model", "haiku", "-"],
    input=prompt,
    capture_output=True,
    text=True,
    env={**os.environ, "HOME": os.environ.get("CLAUDE_HOME", os.path.expanduser("~"))}
)
if result.returncode != 0:
    raise LLMError(f"Claude CLI failed: {result.stderr}")
# Parse JSON from stdout (may contain preamble text before JSON)
json_match = re.search(r'[\[\{].*[\]\}]', result.stdout, re.DOTALL)
if not json_match:
    raise LLMError(f"No JSON found in LLM response")
parsed = json.loads(json_match.group())
```

---

## DB 쿼리 (Resume Service가 직접 실행)

```sql
-- Stage 1: Target NOC 요구 스킬 (category별 top 10, seniority 필터)
-- ROW_NUMBER로 각 category에서 top 10만 추출
SELECT name, category, demand_count FROM (
  SELECT sk.name, sk.category, COUNT(*) as demand_count,
         ROW_NUMBER() OVER (PARTITION BY sk.category ORDER BY COUNT(*) DESC) as rn
  FROM fact_job_skill_demand f
  JOIN fact_job_postings p ON f.job_id = p.job_id
  JOIN dim_skills sk ON f.skill_id = sk.id
  JOIN dim_seniority ds ON p.seniority_id = ds.id
  WHERE p.noc_id = (SELECT id FROM noc_titles WHERE noc21_code = :noc_code)
    AND ds.level = :seniority
  GROUP BY sk.name, sk.category
) ranked WHERE rn <= 10
ORDER BY category, demand_count DESC;

-- Section 2: 전체 NOC 유사도 (내 스킬과 교집합)
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
WHERE sk.name IN (:user_skills)
GROUP BY n.noc21_code, n.noc21_name, total.cnt
ORDER BY match_rate DESC
LIMIT 5;

-- Section 3: 가장 유사한 job posting
SELECT p.job_id, c.name as company, p.raw_title, p.description,
       COUNT(*) as skill_overlap
FROM fact_job_postings p
JOIN dim_companies c ON p.company_id = c.id
JOIN fact_job_skill_demand f ON f.job_id = p.job_id
JOIN dim_skills sk ON f.skill_id = sk.id
WHERE p.noc_id = (SELECT id FROM noc_titles WHERE noc21_code = :best_noc_code)
  AND sk.name IN (:user_skills)
GROUP BY p.job_id, c.name, p.raw_title, p.description
ORDER BY skill_overlap DESC
LIMIT 1;
```

---

## LLM 호출 (3회)

| # | Stage | 목적 | Input | Output |
|---|-------|------|-------|--------|
| 1 | 2 | 자유 스킬 추출 | resume text | `["python", "aws", ...]` |
| 2 | 3 | DB 스킬 reconcile | resume + DB 스킬 목록 (category별 top 10) | `{"matched": [...], "missing": [...]}` |
| 3 | 7 | 종합 분석 생성 | 전체 context (자유 추출 + reconcile + best JD) | strengths, gaps, recommendations, JD highlight |

**왜 3회인가:**
- Prompt 1 (자유 추출): resume에 어떤 스킬이 있는지 파악 — DB에 없는 스킬도 포함
- Prompt 2 (reconcile): DB 이름 기준으로 exact match 보장 — "이 목록에서 골라줘"
- Prompt 3 (분석): 두 결과를 종합해서 인사이트 생성

Prompt 1과 2를 합치면 안 되는 이유: 자유 추출 결과는 similar NOCs 쿼리에 사용되고, reconcile 결과는 target NOC match rate에 사용됨. 목적이 다름.

---

## Project Structure

```
Giljobi-ResumeService/
├── SPEC.md                # 이 문서
├── Dockerfile             # FastAPI + Claude CLI
├── requirements.txt       # Python dependencies
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app + WebSocket endpoint
│   ├── api/
│   │   ├── __init__.py
│   │   └── analyze.py     # /ws/analyze WebSocket handler
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm.py         # Claude CLI subprocess wrapper
│   │   ├── matcher.py     # Skill matching logic (DB queries)
│   │   └── resume.py      # Resume parsing (PDF/text)
│   └── db/
│       ├── __init__.py
│       └── neon.py         # Neon DB connection (market-trend + skill-demand)
├── tests/
│   ├── __init__.py
│   ├── test_matcher.py
│   └── test_llm.py
├── infra/
│   └── aca.tf             # Azure Container Apps Terraform
└── .gitignore
```

---

## Deployment

### Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker

```bash
docker build -t giljobi-resume-service .
docker run -p 8000:8000 \
  -e NEON_MT_DB_URL=postgresql://... \
  -e NEON_SD_DB_URL=postgresql://... \
  giljobi-resume-service
```

### Azure Container Apps

```bash
# Build + push to registry
docker build -t <registry>/giljobi-resume-service:latest .
docker push <registry>/giljobi-resume-service:latest

# Deploy via Terraform (infra/aca.tf)
cd infra && terraform apply

# Scale for demo
az containerapp update --name giljobi-resume \
  --resource-group giljobi-rg \
  --min-replicas 1 --max-replicas 3

# Scale down after demo
az containerapp update --name giljobi-resume \
  --resource-group giljobi-rg \
  --min-replicas 0 --max-replicas 1
```

---

## Test Plan

### Unit Tests (`tests/`)

#### `test_matcher.py` — DB 쿼리 + 스킬 매칭 로직

| # | Test | Input | Expected |
|---|------|-------|----------|
| 1 | `test_get_noc_required_skills` | noc_code="21231", seniority="senior" | list of `{name, category, demand_count}`, len > 0 |
| 2 | `test_get_noc_required_skills_invalid_noc` | noc_code="99999" | empty list |
| 3 | `test_calculate_match_rate` | user_skills=["python","aws"], required=["python","aws","k8s"] | `{match_rate: 0.67, matched: ["python","aws"], missing: ["k8s"]}` |
| 4 | `test_calculate_match_rate_no_overlap` | user_skills=["go"], required=["python","aws"] | `{match_rate: 0.0, matched: [], missing: ["python","aws"]}` |
| 5 | `test_calculate_match_rate_full_match` | user_skills=["python","aws"], required=["python","aws"] | `{match_rate: 1.0, matched: [...], missing: []}` |
| 6 | `test_find_similar_nocs` | user_skills=["python","sql","aws"] | list of 5 `{noc_code, noc_name, match_rate, overlap}`, sorted by match_rate DESC |
| 7 | `test_find_similar_nocs_no_skills` | user_skills=[] | empty list |
| 8 | `test_find_best_posting` | noc_code="21231", user_skills=["python","aws"] | `{company, title, description, skill_overlap}`, skill_overlap > 0 |
| 9 | `test_find_best_posting_no_match` | noc_code="21231", user_skills=["nonexistent_skill"] | None or empty |

#### `test_llm.py` — Claude CLI wrapper

| # | Test | Method | Expected |
|---|------|--------|----------|
| 1 | `test_extract_skills_valid_resume` | mock subprocess → `'["python","aws"]'` | `["python","aws"]` |
| 2 | `test_extract_skills_empty_resume` | mock subprocess → `'[]'` | `[]` |
| 3 | `test_extract_skills_invalid_json` | mock subprocess → `'not json'` | raises `LLMError` |
| 4 | `test_extract_skills_cli_failure` | mock subprocess → returncode=1 | raises `LLMError` |
| 5 | `test_generate_analysis_valid` | mock subprocess → valid JSON | dict with strengths, gaps, recommendations, jd_highlighted |
| 6 | `test_generate_analysis_invalid_json` | mock subprocess → `'not json'` | raises `LLMError` |
| 7 | `test_json_extraction_with_preamble` | mock subprocess → `'Here is the result:\n["python"]'` | `["python"]` (regex extracts JSON from preamble) |

#### `test_validation.py` — 입력 검증

| # | Test | Input | Expected |
|---|------|-------|----------|
| 1 | `test_valid_input` | resume 100 chars, seniority="senior", noc="21231" | passes |
| 2 | `test_resume_too_short` | resume 10 chars | raises `ValidationError("INVALID_INPUT")` |
| 3 | `test_resume_too_long` | resume 60,000 chars | raises `ValidationError("INVALID_INPUT")` |
| 4 | `test_invalid_seniority` | seniority="manager" | raises `ValidationError("INVALID_SENIORITY")` |
| 5 | `test_empty_seniority` | seniority="" | raises `ValidationError("INVALID_SENIORITY")` |
| 6 | `test_invalid_noc_format` | noc="abc" | raises `ValidationError("INVALID_NOC")` |

#### `test_neon.py` — DB 연결

| # | Test | Method | Expected |
|---|------|--------|----------|
| 1 | `test_connect_skill_demand_db` | real Neon connection | SELECT 1 succeeds |
| 2 | `test_connect_market_trend_db` | real Neon connection | SELECT 1 succeeds |
| 3 | `test_noc_exists` | noc_code="21231" | True |
| 4 | `test_noc_not_exists` | noc_code="99999" | False |

### Integration Tests

#### `test_websocket.py` — E2E WebSocket flow

| # | Test | Input | Expected |
|---|------|-------|----------|
| 1 | `test_full_flow_happy_path` | valid resume + seniority + noc | receives all 7 stages in order, final stage="done" |
| 2 | `test_invalid_input_returns_error` | resume="" | receives `{"stage":"error","code":"INVALID_INPUT"}`, WS closed |
| 3 | `test_invalid_noc_returns_error` | noc="99999" | receives extracted stage, then `{"stage":"error","code":"INVALID_NOC"}` |
| 4 | `test_health_endpoint` | GET /health | 200, `{"status":"ok",...}` |
| 5 | `test_noc_list_endpoint` | GET /noc-list | 200, array of `{noc_code, noc_name}`, len == 510 |
| 6 | `test_partial_results_on_error` | mock LLM fail at stage 5 | stages 1-4 received, then error, WS closed |

### Test Strategy

- **Unit tests**: mock DB + mock subprocess → 빠르고 CI에서 실행 가능
- **Integration tests**: 실제 Neon DB + mock LLM → DB 쿼리 정확성 검증
- **E2E tests**: 실제 Neon DB + 실제 Claude CLI → 전체 흐름 검증 (로컬에서만, CI에서는 skip)
- **TDD flow**: test_validation → test_matcher → test_llm → test_websocket 순서로

```
tests/
├── __init__.py
├── test_validation.py      ← 먼저 (입력 검증, 외부 의존성 없음)
├── test_matcher.py          ← 두 번째 (DB 쿼리, mock 또는 real Neon)
├── test_llm.py              ← 세 번째 (Claude CLI, mock subprocess)
├── test_neon.py             ← DB 연결 검증 (integration)
└── test_websocket.py        ← 마지막 (E2E, 전부 조합)
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEON_MT_DB_URL` | Neon market-trend DB connection string (NOC titles) |
| `NEON_SD_DB_URL` | Neon skill-demand DB connection string (star schema) |
| `CLAUDE_HOME` | Claude CLI credentials directory (default: `~/.claude`) |

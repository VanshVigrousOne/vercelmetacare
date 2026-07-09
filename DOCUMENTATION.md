# MetaCare — Technical Documentation

## 1. Overview

MetaCare is a rural diabetes-management platform built around four roles that form a care escalation chain:

```
Patient  →  CHW (Community Health Worker)  →  Doctor
                     ↑
              Dietician (diet/exercise only, cross-cutting)
```

A patient submits a daily log (blood sugar, medication status, free-text symptoms — often Hinglish). Gemini analyzes it, produces a CHW-facing summary and a doctor-facing clinical note, classifies severity, and — for critical cases — automatically raises a Doctor Alert. CHWs validate reports after calling the patient, which can further escalate into a clinic-visit request that a Doctor accepts and schedules.

---

## 2. Architecture

```
┌─────────────┐        REST + JWT        ┌────────────────────┐        REST        ┌──────────────┐
│  index.html │  ───────────────────────▶│   FastAPI backend  │ ──────────────────▶│ Gemini 1.5    │
│ (vanilla JS │◀───────────────────────  │     (main.py)      │◀────────────────── │ Flash API     │
│    SPA)     │                          └─────────┬──────────┘                    └──────────────┘
└─────────────┘                                    │
                                          SQLAlchemy ORM
                                                    │
                                          ┌─────────▼──────────┐
                                          │  SQLite / Postgres  │
                                          └────────────────────┘
```

- **Frontend**: a single `index.html` with embedded CSS/JS. No build tooling, no framework — talks to the backend via `fetch()`, stores the JWT in `sessionStorage`.
- **Backend**: FastAPI app (`main.py`) exposing role-guarded REST endpoints, backed by SQLAlchemy models and Pydantic schemas.
- **AI layer**: `ai_service.py` wraps all Gemini calls. Every function has a hardcoded **fallback response** so the app degrades gracefully (e.g. "Manual review needed") if the Gemini API is unreachable or misconfigured, rather than crashing a clinical workflow.
- **Auth**: stateless JWT bearer tokens (`auth.py`), 24-hour expiry, role embedded in the token payload (`role`, `sub`).

---

## 3. Roles & Permissions

| Role | Can do | Cannot do |
|---|---|---|
| **Patient** | Submit daily logs, view own record/logs/prescriptions/notifications, request a visit for themselves, log food, accept consent | See other patients, validate/resolve tasks |
| **CHW** | View/validate/resolve tasks for their assigned patients, register patients, issue prescription *suggestions*, request/manage visits, set diet plans & exercise | Access another CHW's patients directly (enforced per-endpoint) |
| **Dietician** | **Scoped only to**: diet plans, food logs, exercise plan, and a slim `PatientOverviewOut` (no address/email/referral/prescriptions/tasks/alerts) | View prescriptions, tasks, alerts, or full patient chart |
| **Doctor** | Everything a CHW can do, plus: issue prescriptions, resolve alerts, accept visit requests, register CHWs/Dieticians, deep AI analysis | — (top of hierarchy) |

Authorization is enforced via FastAPI dependencies in `auth.py`:
`require_patient`, `require_chw` (chw+doctor), `require_doctor`, `require_dietician` (dietician+doctor), `require_diet_access` (chw+doctor+dietician).

---

## 4. Data Model

Core entities (see `models.py` for full column list):

- **Doctor** → has many CHWs, Dieticians, Patients, Alerts
- **CHW** → belongs to a Doctor, has many Patients, CHWTasks
- **Dietician** → belongs to a Doctor, has many Patients (restricted relationship — a patient can have *both* a CHW and a Dietician simultaneously)
- **Patient** → belongs to a Doctor + CHW (+ optional Dietician); has many DailyLogs, Prescriptions, CHWTasks, DoctorAlerts, Notifications, PatientEvents, ClinicVisits, DietPlans, LabTests, FoodLogs
- **DailyLog** — patient-submitted blood sugar / medication / weight / free-text entry
- **CHWTask** — created from a DailyLog (or prescription/emergency event); carries the AI classification, summary, and CHW validation notes
- **DoctorAlert** — escalation to a doctor; `source` distinguishes `System` (auto sugar threshold), `AutoTrend` (AI weekly trend), `CHW` (manual escalation), `VisitRequest`/`PatientVisitRequest` (visit escalation)
- **ClinicVisit** — mandatory/impromptu/emergency visits, with scheduling, outcome notes, vitals, and doctor-acceptance state
- **DietPlan** — structured Indian-diet plan (per meal-slot), created by Doctor/CHW/Dietician, optionally CHW-validated
- **LabTest** — ordered/completed lab work, flagged abnormal or not
- **FoodLog** — simple calorie/protein food diary
- **Notification** — patient-facing message feed (Hinglish)
- **PatientEvent** — audit-style event log (`DAILY_LOG`, `PATIENT_REPORT`, `ESCALATION`, `VISIT`, `DIET`, `TEST`)

---

## 5. AI Service (`ai_service.py`)

All functions call a shared `_call()` helper that hits the Gemini `generateContent` endpoint, strips Markdown code fences, and parses JSON — falling back to a safe default dict (with an `"error"` key attached) on any failure.

| Function | Purpose |
|---|---|
| `analyze_patient_report()` | Classifies a new daily log/report: `Routine` / `Needs Follow Up` / `Emergency`, extracts symptoms, translates Hinglish, drafts CHW + doctor summaries |
| `validate_chw_task()` | Re-evaluates a task after a CHW has called the patient, can flag `should_escalate_visit` |
| `generate_trend_alert()` | Weekly/on-demand trend analysis across recent logs + missed meds; decides whether to alert the doctor or schedule a visit |
| `deep_doctor_analysis()` | Free-form clinical Q&A for a doctor investigating a specific alert |
| `generate_diet_plan()` | Produces a full Indian-diet plan tailored to HbA1c, weight, and recent sugar trend |
| `chatbot_response()` | In-app assistant, strictly scoped to MetaCare/diabetes topics, with hardcoded emergency phrasing (`"TURANT 108 call karein..."`) and a refusal to give drug dosages |

**Model**: `gemini-1.5-flash`, configured via `GEMINI_API_KEY` env var — no key is ever hardcoded in source.

---

## 6. API Reference (summary)

Full interactive docs are auto-generated by FastAPI at `/docs` (Swagger) once the server is running. Grouped by tag:

- **Auth** — `POST /auth/token`
- **Doctor** — register, `/doctors/me`, list patients/CHWs/dieticians
- **CHW** — register, `/chws/me`, list patients/tasks
- **Dietician** — register, `/dieticians/me`, list patients, available-patients, self-assign
- **Patient** — register, `/patients/me`, `/patients/{id}`, consent
- **Logs** — submit/get daily logs (triggers AI + task + possible alert)
- **Prescriptions** — issue (Doctor), list per patient
- **Tasks** — list, validate, resolve, escalate
- **Alerts** — list, resolve
- **Visits** — request, accept, create, list per patient, update
- **Notifications** — send, list, mark read
- **AI** — `/ai/deep-analysis`, `/ai/trend-check/{patient_id}`, `/ai/raw` (server-side proxy so the Gemini key never reaches the browser)
- **Diet** — create/list/update diet plans, food logs
- **Exercise** — update patient exercise plan
- **Tests** — order/list/update lab tests

---

## 7. Local Development Notes

- Default DB is SQLite (`metacare.db`, created automatically on first run via `Base.metadata.create_all`)
- `seed.py` is idempotent — it checks for an existing Doctor row and skips seeding if the DB is already populated
- `test_gemini.py` is a standalone diagnostic script to confirm your `GEMINI_API_KEY` is valid and see which models it can access — not part of the running app
- CORS currently allows all origins (`allow_origins=["*"]`) for ease of local development — restrict this before any public deployment

---

## 8. Suggested `.gitignore`

```gitignore
# Environment
.env
*.env

# Database
*.db
metacare.db

# Python
__pycache__/
*.pyc
venv/
.venv/

# OS
.DS_Store
```

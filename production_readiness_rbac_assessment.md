# MetaCare Production-Readiness & RBAC Assessment

MetaCare is an AI-assisted diabetes management platform designed for rural India. This document assesses the system's **Role-Based Access Control (RBAC)** implementation, documents recent security hardening measures (specifically around **Broken Object Level Authorization / BOLA**), and outlines the remaining steps required for a secure production deployment.

---

## 1. Role-Based Access Control (RBAC) Model

MetaCare enforces strict role-based isolation. The care loop follows a hierarchical structure:
```
Patient ──▶ CHW (Community Health Worker) ──▶ Doctor
                 ▲
                 │ (Diet / Exercise plans only)
             Dietician
```

### Permission Matrix

| Feature Area | Endpoint | Patient | CHW | Dietician | Doctor |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Authentication** | `POST /auth/token` | Read/Write | Read/Write | Read/Write | Read/Write |
| **Doctor Registration** | `POST /doctors/register` | 🚫 | 🚫 | 🚫 | Read/Write |
| **Provider Directory** | `GET /doctors/{id}/patients` / `chws` | 🚫 | 🚫 | 🚫 | Read (Own) |
| **CHW Registration** | `POST /chws/register` | 🚫 | 🚫 | 🚫 | Write (Own) |
| **Dietician Registration** | `POST /dieticians/register` | 🚫 | 🚫 | 🚫 | Write (Own) |
| **Patient Registration** | `POST /patients/register` | 🚫 | Write | 🚫 | Write |
| **Patient Chart View** | `GET /patients/{id}` | Read (Self) | Read (Assigned) | Read (Diet-only) | Read (Assigned) |
| **Daily Logs Submit** | `POST /patients/{id}/logs` | Write (Self) | 🚫 | 🚫 | 🚫 |
| **Prescription Issuance** | `POST /prescriptions` | 🚫 | 🚫 | 🚫 | Write (Own) |
| **Prescription View** | `GET /patients/{id}/prescriptions` | Read (Self) | Read (Assigned) | 🚫 | Read (Assigned) |
| **CHW Task Validation** | `POST /tasks/{id}/validate` | 🚫 | Write (Assigned) | 🚫 | Write (Assigned) |
| **Doctor Alerts** | `GET /alerts` / `POST /alerts/{id}/resolve`| 🚫 | Read (Assigned) | 🚫 | Write (Own) |
| **Visit Escalation** | `POST /patients/{id}/request-visit` | Write (Self) | Write (Assigned) | 🚫 | Write (Assigned) |
| **Diet Plan Management** | `POST /diet-plans` / `PUT /diet-plans/{id}`| 🚫 | Write (Assigned) | Write (Assigned) | Write (Assigned) |
| **Raw AI Proxy API** | `POST /ai/raw` | 🚫 | 🚫 | 🚫 | Read/Write |

---

## 2. BOLA & IDOR Mitigation Status (Security Hardening)

A comprehensive security audit was completed to resolve Broken Object Level Authorization (BOLA/IDOR) vulnerabilities where users could access or edit patient records not assigned to their care team.

### Vulnerabilities Audited & Remedied

> [!NOTE]
> **Task Validation & Escalation Hardening**
> - **Endpoints**: `POST /tasks/{task_id}/validate`, `/tasks/{task_id}/resolve`, `/tasks/{task_id}/escalate`
> - **Vulnerability**: Any CHW or Doctor could validate/resolve/escalate tasks of *any* patient.
> - **Remedy**: Added relationship verification. CHWs are now strictly checked against `task.chw_id == user.id`. Doctors are verified against `patient.doctor_id == user.id`.

> [!NOTE]
> **Doctor Alert & Visit Acceptance Hardening**
> - **Endpoints**: `POST /alerts/{alert_id}/resolve`, `POST /alerts/{alert_id}/accept-visit`
> - **Vulnerability**: Any Doctor could resolve alerts or schedule visits for another Doctor's patients.
> - **Remedy**: Added checks to ensure the alert belongs directly to the calling doctor: `alert.doctor_id == doctor.id`.

> [!NOTE]
> **Visit Escalation Scoping**
> - **Endpoint**: `POST /patients/{patient_id}/request-visit`
> - **Vulnerability**: Providers could request/escalate clinic visits for unassigned patients.
> - **Remedy**: Verified that CHWs are assigned to the patient (`patient.chw_id == user.id`) and Doctors supervise the patient (`patient.doctor_id == user.id`).

> [!NOTE]
> **Dietician & Care Team Assignment Scoping**
> - **Endpoint**: `PUT /patients/{patient_id}/dietician`
> - **Vulnerability**: Doctors and CHWs from different practices could assign Dieticians to patients under other practices.
> - **Remedy**: Enforced that Doctors can only assign Dieticians under their own registry (`dietician.doctor_id == user.id` and `patient.doctor_id == user.id`). CHWs can only assign Dieticians registered under their supervising doctor (`dietician.doctor_id == user.doctor_id` and `patient.chw_id == user.id`).

> [!WARNING]
> **Raw AI Proxy Endpoint Scoping**
> - **Endpoint**: `POST /ai/raw`
> - **Vulnerability**: The raw Gemini proxy endpoint allowed any authenticated user (including patients) to send arbitrary prompts, exposing the API to prompt injection and billing abuse.
> - **Remedy**: Restricted the endpoint strictly to the **Doctor** role using `auth.require_doctor`.

---

## 3. Core Cryptography & Environment Protections

We verified the underlying infrastructure and cryptography layers:
1. **Password Hashing**: Upgraded credential hashing from `passlib` context to direct, robust `bcrypt` using 12 salt rounds (`bcrypt.hashpw` / `bcrypt.checkpw`). This eliminates vulnerabilities associated with legacy wrapper frameworks.
2. **Environment Isolation**: Configured FastAPI startup sequence to load `.env` variables safely (`python-dotenv`), ensuring that secrets (`JWT_SECRET_KEY` and `GEMINI_API_KEY`) are kept out of source code.
3. **AI Fallback Resilience**: Confirmed that all calls in `ai_service.py` wrap Gemini API connections with exception-catching blocks and return safe, pre-defined fallback dictionaries (e.g., triage defaults to `Routine` with a manual review notice) to prevent system hangs.

---

## 4. Production Go-Live Checklist

Before deploying the MetaCare platform to staging or production, the following steps must be completed:

### ⚙️ Environment Configuration
- [ ] **Rotate Secret Keys**: Generate a fresh, high-entropy `JWT_SECRET_KEY` using `secrets.token_hex(32)`.
- [ ] **Store Secrets Safely**: Inject keys (`JWT_SECRET_KEY`, `GEMINI_API_KEY`) using the host's native environment variable manager (e.g., AWS Secrets Manager, GitHub Secrets, or Cloud Run Environment variables). Do not commit `.env` files.

### 🗄️ Database & Storage
- [ ] **Migrate to PostgreSQL**: Swap the local SQLite instance (`metacare.db`) for a production-grade managed database (e.g., AWS RDS Postgres or Google Cloud SQL) by updating the database URL connection string in `database.py`.
- [ ] **Backup Schedule**: Enable daily automated database backups with a minimum retention period of 30 days.

### 🌐 Networking & Security
- [ ] **Lock Down CORS Origins**: In `main.py`, replace `allow_origins=["*"]` in the CORS middleware with a strict list of allowed production frontend domains.
- [ ] **Enforce HTTPS**: Route all backend APIs and frontend assets through TLS/HTTPS (SSL). Enable HTTP Strict Transport Security (HSTS).
- [ ] **Rate Limiting**: Implement basic API rate-limiting (e.g., using `slowapi` or Nginx reverse-proxy limits) to protect against Denial-of-Service (DoS) and brute-force login attempts.

### 📊 Monitoring & Logging
- [ ] **Structured Logging**: Configure backend logs to output in JSON format to a centralized logging collector (e.g., CloudWatch or Google Cloud Logging).
- [ ] **Error Tracking**: Integrate Sentry or a similar APM tool in FastAPI to monitor runtime exceptions and receive alerts for API or LLM connection failures.

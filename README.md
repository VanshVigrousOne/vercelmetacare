# MetaCare

**AI-assisted diabetes management for rural India.**

MetaCare connects **Patients**, **Community Health Workers (CHWs)**, **Dieticians**, and **Doctors** in a single care loop. Patients log symptoms and blood sugar in Hinglish; an AI layer (Google Gemini) classifies severity, summarises for the care team, and drafts diet plans — while CHWs and Doctors stay in control of every clinical decision.

---

## ✨ Key Features

- **Role-based care team** — Patient, CHW, Dietician, Doctor, each with scoped permissions
- **AI-powered triage** — patient reports are auto-classified (`Routine` / `Needs Follow Up` / `Emergency`) with a plain-language CHW summary and clinical doctor context
- **Trend monitoring** — automatic alerts to doctors on worsening sugar trends or missed medication
- **Visit escalation workflow** — CHWs (or patients) can request a clinic visit; doctors accept and schedule it
- **AI diet plans** — auto-generated, practical Indian-diet plans, validated by CHW/Dietician
- **Lab test tracking**, **food diary**, **exercise plans**, and **in-app notifications**
- **Embedded chatbot** for patients/CHWs, scoped strictly to MetaCare & diabetes topics
- **Consent tracking** — patients must accept Terms & Conditions before use

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Backend API | **FastAPI** (Python 3) |
| ORM / Database | **SQLAlchemy** + **SQLite** (swappable to PostgreSQL) |
| Auth | **JWT** (python-jose) + **bcrypt** (passlib) |
| AI | **Google Gemini 1.5 Flash** (`google-generativeai` / REST via `httpx`) |
| Data validation | **Pydantic** (schemas) |
| Frontend | Single-file **vanilla JS SPA** (`index.html`, no framework/build step) |
| Env config | `python-dotenv` |

See [`DOCUMENTATION.md`](./DOCUMENTATION.md) for full architecture, data model, and API reference.

---

## 🚀 Getting Started

### 1. Clone & install
```bash
git clone <your-repo-url>
cd metacare
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install fastapi uvicorn sqlalchemy python-jose[cryptography] passlib[bcrypt] httpx python-dotenv google-generativeai
```

### 2. Configure environment
Create a `.env` file in the project root (this file is git-ignored — see below):
```env
JWT_SECRET_KEY=replace-with-a-long-random-string
GEMINI_API_KEY=your-gemini-api-key
```
Generate a strong secret with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Seed demo data (optional but recommended)
```bash
python seed.py
```
This creates one Doctor, one CHW, one Dietician, and two demo Patients with 14 days of realistic logs. Credentials are printed to the console — **these are for local demo use only.**

### 4. Run the backend
```bash
uvicorn main:app --reload
```
API docs (Swagger UI) will be live at `http://localhost:8000/docs`.

### 5. Run the frontend
Open `index.html` directly in a browser, or serve it:
```bash
python -m http.server 5500
```
By default it points at `BACKEND = 'http://localhost:8000'` in `index.html` — update this for any non-local deployment.

---

## 🔐 Before Deploying to Production

- [ ] Set `JWT_SECRET_KEY` and `GEMINI_API_KEY` via your host's secret manager (never commit `.env`)
- [ ] Replace SQLite with PostgreSQL (`DATABASE_URL` in `database.py`)
- [ ] Lock down `allow_origins=["*"]` in `main.py`'s CORS middleware to your real frontend domain(s)
- [ ] Update `BACKEND` in `index.html` to your production API URL
- [ ] Rotate/remove the demo seed passwords — don't run `seed.py` against production
- [ ] Put the app behind HTTPS

---

## 📁 Project Structure

```
.
├── main.py           # FastAPI app & all API routes
├── models.py         # SQLAlchemy ORM models
├── schemas.py        # Pydantic request/response schemas
├── auth.py           # JWT auth, password hashing, role guards
├── database.py       # DB engine/session config
├── ai_service.py      # All Gemini API calls (triage, diet plans, chatbot, etc.)
├── seed.py           # Demo data seeder
├── test_gemini.py    # Standalone script to verify your Gemini API key works
└── index.html         # Frontend SPA (vanilla JS, no build step)
```

---

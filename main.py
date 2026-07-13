"""
main.py – MetaCare FastAPI backend
Roles: Patient · CHW · Doctor · Dietician
Auth:  JWT tokens via /auth/token
"""

import os
import sys
import logging
from pythonjsonlogger import jsonlogger
from dotenv import load_dotenv

# Load environment variables on startup
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, status, Body, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional, Union
import models, schemas, auth, ai_service, diet_reference
from database import engine, Base, get_db
from pydantic import BaseModel

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import sentry_sdk

sentry_sdk.init(
    dsn=os.environ.get("SENTRY_DSN"),
    send_default_pii=True,
    enable_logs=True,
    traces_sample_rate=1.0,
    profile_session_sample_rate=1.0,
    profile_lifecycle="trace",
)
# ---------------------------------------------------------------------------
# Structured (JSON) logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("metacare")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_log_handler = logging.StreamHandler(sys.stdout)
_log_formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
)
_log_handler.setFormatter(_log_formatter)
logger.handlers = [_log_handler]
logger.propagate = False

# Create all tables on startup
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Lightweight auto-migration (SQLite + Postgres): create_all() won't add new
# columns to tables that already exist, so patch them in here if missing.
# Works against both dialects — SQLite (local/dev fallback) and Postgres
# (Neon, in production) — since the two use different introspection syntax.
# ---------------------------------------------------------------------------
def _run_auto_migrations():
    try:
        with engine.connect() as conn:
            is_sqlite = engine.dialect.name == "sqlite"
            if is_sqlite:
                cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(clinic_visits)").fetchall()]
            else:
                cols = [
                    row[0] for row in conn.exec_driver_sql(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = 'clinic_visits'"
                    ).fetchall()
                ]

            if "duration_minutes" not in cols:
                stmt = "ALTER TABLE clinic_visits ADD COLUMN " + (
                    "duration_minutes INTEGER DEFAULT 30" if is_sqlite
                    else "IF NOT EXISTS duration_minutes INTEGER DEFAULT 30"
                )
                conn.exec_driver_sql(stmt)
            if "meeting_id" not in cols:
                stmt = "ALTER TABLE clinic_visits ADD COLUMN " + (
                    "meeting_id VARCHAR" if is_sqlite
                    else "IF NOT EXISTS meeting_id VARCHAR"
                )
                conn.exec_driver_sql(stmt)
            conn.commit()
    except Exception as exc:
        logger.warning(f"Skipping auto-migration check: {exc}")

_run_auto_migrations()

app = FastAPI(
    title="MetaCare API",
    description="Rural diabetes management — Patient · CHW · Doctor",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS — locked down to explicit production origins.
# Set ALLOWED_ORIGINS in the environment as a comma-separated list, e.g.:
#   ALLOWED_ORIGINS=https://app.metacare.org,https://admin.metacare.org
# Falls back to localhost dev origins only if the env var is not set.
# ---------------------------------------------------------------------------
_default_dev_origins = "http://localhost:3000,http://127.0.0.1:3000"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", _default_dev_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Rate limiting (slowapi) — protects the API from brute-force login attempts
# and general DoS abuse. Override per-route with @limiter.limit("...").
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a single human-readable message instead of FastAPI's raw error list,
    so the frontend can show it directly to the user."""
    first = exc.errors()[0] if exc.errors() else None
    message = first["msg"] if first else "Invalid input."
    # Pydantic v2 prefixes custom ValueError messages with "Value error, "
    if message.startswith("Value error, "):
        message = message[len("Value error, "):]
    return JSONResponse(status_code=422, content={"detail": message})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "client": request.client.host if request.client else None,
        },
    )
    return response


#  Helpers

def _log_to_dict(log: models.DailyLog) -> dict:
    return {
        "date": log.created_at.isoformat(),
        "sugar": log.blood_sugar,
        "meds": log.medication_taken,
        "text": log.raw_text,
    }



# AUTH


@app.post("/auth/token", response_model=schemas.TokenResponse, tags=["Auth"])
@limiter.limit("10/minute")
def login(request: Request, payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Login for Patient, CHW, or Doctor. Returns JWT."""
    role = payload.role.lower()

    if role == "patient":
        user = db.query(models.Patient).filter(models.Patient.phone == payload.phone).first()
    elif role == "chw":
        user = db.query(models.CHW).filter(models.CHW.phone == payload.phone).first()
    elif role == "dietician":
        user = db.query(models.Dietician).filter(models.Dietician.phone == payload.phone).first()
    elif role == "doctor":
        user = db.query(models.Doctor).filter(models.Doctor.phone == payload.phone).first()
    else:
        raise HTTPException(status_code=400, detail="role must be patient | chw | dietician | doctor")

    if not user or not auth.verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid phone or password")

    token = auth.create_access_token({"sub": str(user.id), "role": role})
    return schemas.TokenResponse(
        access_token=token,
        role=role,
        user_id=user.id,
        name=user.name,
    )


# DOCTOR REGISTRATION & MANAGEMENT


@app.post("/doctors/register", response_model=schemas.DoctorOut, tags=["Doctor"])
def register_doctor(payload: schemas.DoctorCreate, db: Session = Depends(get_db)):
    if db.query(models.Doctor).filter(models.Doctor.phone == payload.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered")
    doctor = models.Doctor(
        name=payload.name,
        specialization=payload.specialization,
        hospital=payload.hospital,
        phone=payload.phone,
        hashed_password=auth.hash_password(payload.password),
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


@app.get("/doctors/me", response_model=schemas.DoctorOut, tags=["Doctor"])
def get_me_doctor(doctor: models.Doctor = Depends(auth.require_doctor)):
    return doctor


@app.get("/doctors/{doctor_id}/patients", response_model=List[schemas.PatientOut], tags=["Doctor"])
def list_doctor_patients(
    doctor_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    if doctor.id != doctor_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return db.query(models.Patient).filter(models.Patient.doctor_id == doctor_id).all()


@app.get("/doctors/{doctor_id}/chws", response_model=List[schemas.CHWOut], tags=["Doctor"])
def list_doctor_chws(
    doctor_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    if doctor.id != doctor_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return db.query(models.CHW).filter(models.CHW.doctor_id == doctor_id).all()


@app.get("/doctors/{doctor_id}/dieticians", response_model=List[schemas.DieticianOut], tags=["Doctor"])
def list_doctor_dieticians(
    doctor_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """Lets a Doctor or CHW see the dieticians under this doctor, to pick one
    when assigning a dietician to a patient."""
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    if role == "doctor" and user.id != doctor_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and user.doctor_id != doctor_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return db.query(models.Dietician).filter(models.Dietician.doctor_id == doctor_id).all()


# CHW REGISTRATION & MANAGEMENT

@app.post("/chws/register", response_model=schemas.CHWOut, tags=["CHW"])
def register_chw(
    payload: schemas.CHWCreate,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    if db.query(models.CHW).filter(models.CHW.phone == payload.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered")
    chw = models.CHW(
        name=payload.name,
        area=payload.area,
        phone=payload.phone,
        doctor_id=doctor.id,
        hashed_password=auth.hash_password(payload.password),
    )
    db.add(chw)
    db.commit()
    db.refresh(chw)
    return chw


@app.get("/chws/me", response_model=schemas.CHWOut, tags=["CHW"])
def get_me_chw(current=Depends(auth.get_current_user)):
    role, user = current
    if role != "chw":
        raise HTTPException(status_code=403, detail="CHW only")
    return user


@app.get("/chws/{chw_id}/patients", response_model=List[schemas.PatientOut], tags=["CHW"])
def list_chw_patients(
    chw_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "chw" and user.id != chw_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "doctor" and not db.query(models.CHW).filter(
        models.CHW.id == chw_id, models.CHW.doctor_id == user.id
    ).first():
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    return db.query(models.Patient).filter(models.Patient.chw_id == chw_id).all()


@app.get("/chws/{chw_id}/tasks", response_model=List[schemas.TaskOut], tags=["CHW"])
def list_chw_tasks(
    chw_id: int,
    status: Optional[str] = "Pending",
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "chw" and user.id != chw_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "doctor" and not db.query(models.CHW).filter(
        models.CHW.id == chw_id, models.CHW.doctor_id == user.id
    ).first():
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    q = db.query(models.CHWTask).filter(models.CHWTask.chw_id == chw_id)
    if status:
        q = q.filter(models.CHWTask.status == status)
    return q.order_by(models.CHWTask.created_at.desc()).all()



# DIETICIAN REGISTRATION & MANAGEMENT
# A Dietician is a restricted, CHW-like role. A patient can be under a CHW
# AND a Dietician at the same time. The Dietician can only see/manage that
# patient's diet plans, food logs, and exercise plan — nothing else
# (no daily logs, tasks, alerts, prescriptions, or visits).

@app.post("/dieticians/register", response_model=schemas.DieticianOut, tags=["Dietician"])
def register_dietician(
    payload: schemas.DieticianCreate,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    if db.query(models.Dietician).filter(models.Dietician.phone == payload.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered")
    dietician = models.Dietician(
        name=payload.name,
        specialization=payload.specialization,
        phone=payload.phone,
        doctor_id=doctor.id,
        hashed_password=auth.hash_password(payload.password),
    )
    db.add(dietician)
    db.commit()
    db.refresh(dietician)
    return dietician


@app.get("/dieticians/me", response_model=schemas.DieticianOut, tags=["Dietician"])
def get_me_dietician(current=Depends(auth.get_current_user)):
    role, user = current
    if role != "dietician":
        raise HTTPException(status_code=403, detail="Dietician only")
    return user


@app.get("/dieticians/{dietician_id}/patients", response_model=List[schemas.PatientOverviewOut], tags=["Dietician"])
def list_dietician_patients(
    dietician_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "dietician" and user.id != dietician_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "doctor" and not db.query(models.Dietician).filter(
        models.Dietician.id == dietician_id, models.Dietician.doctor_id == user.id
    ).first():
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role not in ("dietician", "doctor"):
        raise HTTPException(status_code=403, detail="Dietician or Doctor only")
    return db.query(models.Patient).filter(models.Patient.dietician_id == dietician_id).all()


@app.get("/dieticians/{dietician_id}/available-patients", response_model=List[schemas.PatientOverviewOut], tags=["Dietician"])
def list_available_patients_for_dietician(
    dietician_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """Patients under the same doctor as this dietician, so the dietician can
    pick from the existing roster instead of entering patient details themself."""
    role, user = current
    if role not in ("dietician", "doctor"):
        raise HTTPException(status_code=403, detail="Dietician or Doctor only")
    if role == "dietician" and user.id != dietician_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    dietician = db.query(models.Dietician).filter(models.Dietician.id == dietician_id).first()
    if not dietician:
        raise HTTPException(status_code=404, detail="Dietician not found")
    return db.query(models.Patient).filter(models.Patient.doctor_id == dietician.doctor_id).all()


@app.put("/patients/{patient_id}/dietician", response_model=schemas.PatientOut, tags=["Dietician"])
def assign_dietician(
    patient_id: int,
    payload: schemas.PatientDieticianAssign,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """CHW or Doctor assigns/changes the Dietician for a patient. A Dietician may
    also self-assign to any patient under their own doctor — picking from the
    existing roster rather than entering patient details themself. The patient
    keeps their existing CHW — a Dietician is added on top, not a replacement."""
    role, user = current
    if role not in ("chw", "doctor", "dietician"):
        raise HTTPException(status_code=403, detail="CHW, Doctor, or Dietician only")
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    dietician = db.query(models.Dietician).filter(models.Dietician.id == payload.dietician_id).first()
    if not dietician:
        raise HTTPException(status_code=404, detail="Dietician not found")
    if role == "dietician":
        # A dietician may only assign themself, and only to a patient under their own doctor.
        if user.id != payload.dietician_id:
            raise HTTPException(status_code=403, detail="Dieticians can only assign themselves")
        if patient.doctor_id != user.doctor_id:
            raise HTTPException(status_code=403, detail="Patient is not under your doctor")
    elif role == "doctor":
        if patient.doctor_id != user.id or dietician.doctor_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "chw":
        if patient.chw_id != user.id or dietician.doctor_id != user.doctor_id:
            raise HTTPException(status_code=403, detail="Forbidden")
    patient.dietician_id = dietician.id
    db.commit()
    db.refresh(patient)
    return patient


# PATIENT REGISTRATION & MANAGEMENT


@app.post("/patients/register", response_model=schemas.PatientOut, tags=["Patient"])
def register_patient(
    payload: schemas.PatientCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """CHW or Doctor can register a new patient."""
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="Only CHW or Doctor can register patients")

    # Scoping checks to prevent provider spoofing
    if role == "doctor" and payload.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Cannot register a patient for another doctor")
    if role == "chw":
        if payload.chw_id != user.id:
            raise HTTPException(status_code=403, detail="Cannot register a patient for another CHW")
        if payload.doctor_id != user.doctor_id:
            raise HTTPException(status_code=403, detail="Supervising doctor must match your assigned doctor")

    if db.query(models.Patient).filter(models.Patient.phone == payload.phone).first():
        raise HTTPException(status_code=400, detail="Phone already registered")
    patient = models.Patient(
        name=payload.name,
        age=payload.age,
        gender=payload.gender,
        phone=payload.phone,
        village=payload.village,
        condition=payload.condition,
        hba1c=payload.hba1c,
        weight=payload.weight,
        height_cm=payload.height_cm,
        chw_id=payload.chw_id,
        doctor_id=payload.doctor_id,
        dietician_id=payload.dietician_id,
        hashed_password=auth.hash_password(payload.password),
        title=payload.title,
        dob=payload.dob,
        existing_id=payload.existing_id,
        blood_group=payload.blood_group,
        preferred_language=payload.preferred_language,
        email=payload.email,
        address=payload.address,
        city=payload.city,
        area_pin=payload.area_pin,
        referred_by_name=payload.referred_by_name,
        referred_by_specialization=payload.referred_by_specialization,
        channel=payload.channel,
        care_of=payload.care_of,
        occupation=payload.occupation,
        phone2=payload.phone2,
        tag=payload.tag,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


@app.get("/patients/me", response_model=schemas.PatientOut, tags=["Patient"])
def get_me_patient(patient: models.Patient = Depends(auth.require_patient)):
    return patient


@app.get("/patients/{patient_id}", response_model=Union[schemas.PatientOut, schemas.PatientOverviewOut], tags=["Patient"])
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Scoping checks to prevent BOLA/IDOR
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Dieticians get a slim, diet-relevant overview only — not the full chart
    if role == "dietician":
        return schemas.PatientOverviewOut.model_validate(patient)
    return patient



# CONSENT  (Terms & Conditions)


@app.post("/patients/{patient_id}/consent", response_model=schemas.PatientOut, tags=["Consent"])
def accept_consent(
    patient_id: int,
    payload: schemas.ConsentAccept,
    db: Session = Depends(get_db),
    patient: models.Patient = Depends(auth.require_patient),
):
    """Patient gives consent to MetaCare's Terms & Conditions. Only the patient
    themself can record their own consent."""
    if patient.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not payload.agree:
        raise HTTPException(status_code=400, detail="You must agree to the Terms & Conditions to continue")
    patient.consent_given = True
    patient.consent_given_at = datetime.utcnow()
    patient.consent_version = payload.version
    db.commit()
    db.refresh(patient)
    return patient


# DAILY LOGS  (patient submits report → AI → task → optional alert)


@app.post("/patients/{patient_id}/logs", response_model=schemas.LogOut, tags=["Logs"])
def submit_log(
    patient_id: int,
    payload: schemas.LogCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """Patient submits daily health report. AI classifies and creates CHW task."""
    role, user = current
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Scoping checks to prevent BOLA/IDOR
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "dietician":
        raise HTTPException(status_code=403, detail="Dieticians cannot submit daily medical logs")

    # Save log
    log = models.DailyLog(
        patient_id=patient_id,
        blood_sugar=payload.blood_sugar,
        medication_taken=payload.medication_taken,
        weight=payload.weight,
        raw_text=payload.raw_text,
        logged_by="Patient",
    )
    db.add(log)
    db.flush()

    # Gather recent logs for AI context
    recent = (
        db.query(models.DailyLog)
        .filter(models.DailyLog.patient_id == patient_id)
        .order_by(models.DailyLog.created_at.desc())
        .limit(5)
        .all()
    )
    recent_dicts = [_log_to_dict(l) for l in recent]

    # AI analysis
    ai = ai_service.analyze_patient_report(
        patient_name=patient.name,
        patient_age=patient.age or 0,
        condition=patient.condition or "Type 2 Diabetes",
        report_text=payload.raw_text or "",
        blood_sugar=payload.blood_sugar,
        medication_taken=payload.medication_taken,
        recent_logs=recent_dicts,
    )

    # Simple non-AI sugar threshold check — shown as a plain alert on the CHW page
    critical_sugar = bool(payload.blood_sugar and (payload.blood_sugar < 70 or payload.blood_sugar > 250))

    # CHW task
    chw_task = models.CHWTask(
        patient_id=patient_id,
        chw_id=patient.chw_id,
        task_type="Patient Report",
        status="Pending",
        raw_patient_text=payload.raw_text,
        ai_summary=ai.get("chw_summary"),
        ai_classification=ai.get("classification", "Needs Follow Up"),
        extracted_symptoms=ai.get("extracted_symptoms", []),
        ai_doctor_context=ai.get("doctor_context"),
        ai_suggested_action=ai.get("suggested_action"),
        critical_sugar_alert=critical_sugar,
    )
    db.add(chw_task)
    db.flush()

    # Auto-alert for critical sugar or Emergency classification
    if (payload.blood_sugar and payload.blood_sugar > 300) or ai.get("classification") == "Emergency":
        alert = models.DoctorAlert(
            patient_id=patient_id,
            doctor_id=patient.doctor_id,
            alert_reason=(
                f"Emergency: {', '.join(ai.get('extracted_symptoms', []))}"
                if ai.get("classification") == "Emergency"
                else f"Critical sugar: {payload.blood_sugar} mg/dL"
            ),
            doctor_context=ai.get("doctor_context"),
            source="System",
        )
        db.add(alert)

    # Event log
    db.add(models.PatientEvent(
        patient_id=patient_id,
        event_type="PATIENT_REPORT",
        payload={
            "text": payload.raw_text,
            "sugar": payload.blood_sugar,
            "meds": payload.medication_taken,
            "ai_classification": ai.get("classification"),
        },
        source="Patient",
    ))

    db.commit()
    db.refresh(log)
    return log


@app.get("/patients/{patient_id}/logs", response_model=List[schemas.LogOut], tags=["Logs"])
def get_logs(
    patient_id: int,
    limit: int = 14,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return (
        db.query(models.DailyLog)
        .filter(models.DailyLog.patient_id == patient_id)
        .order_by(models.DailyLog.created_at.desc())
        .limit(limit)
        .all()
    )



# PRESCRIPTIONS


@app.post("/prescriptions", response_model=schemas.PrescriptionOut, tags=["Prescriptions"])
def issue_prescription(
    payload: schemas.PrescriptionCreate,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    """Doctor issues or updates a prescription. Notifies patient and creates CHW task."""
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.doctor_id != doctor.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    # Deactivate existing prescriptions for this patient
    db.query(models.Prescription).filter(
        models.Prescription.patient_id == payload.patient_id,
        models.Prescription.active == True,
    ).update({"active": False})

    rx = models.Prescription(
        patient_id=payload.patient_id,
        medication_name=payload.medication_name,
        dosage=payload.dosage,
        instructions=payload.instructions,
        suggested_by="Doctor",
        active=True,
    )
    db.add(rx)
    db.flush()

    # Notify patient
    db.add(models.Notification(
        patient_id=payload.patient_id,
        sent_by="Doctor",
        sent_by_name=doctor.name,
        message=(
            f"Aapka prescription update hua hai Dr. {doctor.name} dwara: "
            f"{payload.medication_name}, {payload.dosage}. "
            f"{payload.instructions or ''} Aapki CHW aapko jald samjhayegi."
        ),
    ))

    # CHW task to explain prescription
    if patient:
        db.add(models.CHWTask(
            patient_id=payload.patient_id,
            chw_id=patient.chw_id,
            task_type="Prescription Explanation",
            status="Pending",
            ai_summary=(
                f"Doctor issued prescription: {payload.medication_name} — {payload.dosage}. "
                f"{payload.instructions or ''} Please explain the new regimen to {patient.name} in simple terms."
            ),
            ai_classification="Routine",
        ))

    db.commit()
    db.refresh(rx)
    return rx


@app.get("/patients/{patient_id}/prescriptions", response_model=List[schemas.PrescriptionOut], tags=["Prescriptions"])
def get_prescriptions(
    patient_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "dietician":
        raise HTTPException(status_code=403, detail="Dieticians only have access to diet plans, food logs, and exercise plans")
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    q = db.query(models.Prescription).filter(models.Prescription.patient_id == patient_id)
    if active_only:
        q = q.filter(models.Prescription.active == True)
    return q.order_by(models.Prescription.created_at.desc()).all()



# CHW TASKS


@app.get("/tasks", response_model=List[schemas.TaskOut], tags=["Tasks"])
def list_tasks(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "dietician":
        raise HTTPException(status_code=403, detail="Dieticians only have access to diet plans, food logs, and exercise plans")
    q = db.query(models.CHWTask)
    if role == "chw":
        q = q.filter(models.CHWTask.chw_id == user.id)
    elif role == "doctor":
        patient_ids = [p.id for p in db.query(models.Patient).filter(models.Patient.doctor_id == user.id).all()]
        q = q.filter(models.CHWTask.patient_id.in_(patient_ids))
    if status:
        q = q.filter(models.CHWTask.status == status)
    return q.order_by(models.CHWTask.created_at.desc()).all()


@app.post("/tasks/{task_id}/validate", response_model=schemas.TaskOut, tags=["Tasks"])
def validate_task(
    task_id: int,
    payload: schemas.TaskValidate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """CHW validates a task after calling the patient. AI re-evaluates."""
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")

    task = db.query(models.CHWTask).filter(models.CHWTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    patient = db.query(models.Patient).filter(models.Patient.id == task.patient_id).first()
    if role == "chw" and task.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and (patient is None or patient.doctor_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    recent = (
        db.query(models.DailyLog)
        .filter(models.DailyLog.patient_id == task.patient_id)
        .order_by(models.DailyLog.created_at.desc())
        .limit(5)
        .all()
    )

    ai = ai_service.validate_chw_task(
        patient_name=patient.name if patient else "Unknown",
        patient_age=patient.age or 0 if patient else 0,
        original_report=task.raw_patient_text or "",
        initial_ai_summary=task.ai_summary or "",
        chw_note=payload.chw_note,
        recent_logs=[_log_to_dict(l) for l in recent],
    )

    task.chw_validated = True
    task.chw_validated_note = payload.chw_note
    task.ai_summary = ai.get("chw_summary", task.ai_summary)
    task.ai_classification = ai.get("classification", task.ai_classification)
    task.ai_doctor_context = ai.get("doctor_context", task.ai_doctor_context)

    # Escalate to doctor if needed
    if ai.get("classification") in ("Emergency", "Needs Follow Up"):
        db.add(models.DoctorAlert(
            patient_id=task.patient_id,
            doctor_id=patient.doctor_id if patient else None,
            alert_reason=f"CHW Escalation: {ai.get('suggested_action', '')}",
            doctor_context=ai.get("doctor_context"),
            source="CHW",
        ))

    db.commit()
    db.refresh(task)
    return task


@app.post("/tasks/{task_id}/resolve", response_model=schemas.TaskOut, tags=["Tasks"])
def resolve_task(
    task_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    task = db.query(models.CHWTask).filter(models.CHWTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    patient = db.query(models.Patient).filter(models.Patient.id == task.patient_id).first()
    if role == "chw" and task.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and (patient is None or patient.doctor_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    task.status = "Resolved"
    db.commit()
    db.refresh(task)
    return task


@app.post("/tasks/{task_id}/escalate", response_model=schemas.TaskOut, tags=["Tasks"])
def escalate_task(
    task_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    task = db.query(models.CHWTask).filter(models.CHWTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    patient = db.query(models.Patient).filter(models.Patient.id == task.patient_id).first()
    if role == "chw" and task.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and (patient is None or patient.doctor_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    task.status = "Escalated"

    db.add(models.DoctorAlert(
        patient_id=task.patient_id,
        doctor_id=patient.doctor_id if patient else None,
        alert_reason=f"Task escalated by CHW: {task.task_type}",
        doctor_context=(
            f"CHW escalated: {task.ai_summary or ''}"
            + (f" CHW note: {task.chw_validated_note}" if task.chw_validated_note else "")
        ),
        source="CHW",
    ))

    db.commit()
    db.refresh(task)
    return task



# DOCTOR ALERTS


@app.get("/alerts", response_model=List[schemas.AlertOut], tags=["Alerts"])
def list_alerts(
    resolved: bool = False,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "doctor":
        query = db.query(models.DoctorAlert).filter(
            models.DoctorAlert.doctor_id == user.id,
            models.DoctorAlert.source != "PatientVisitRequest",
        )
    elif role == "chw":
        # CHWs only see alerts for patients assigned to them
        query = (
            db.query(models.DoctorAlert)
            .join(models.Patient, models.Patient.id == models.DoctorAlert.patient_id)
            .filter(models.Patient.chw_id == user.id)
        )
    else:
        raise HTTPException(status_code=403, detail="CHW or Doctor only")

    return (
        query.filter(models.DoctorAlert.is_resolved == resolved)
        .order_by(models.DoctorAlert.created_at.desc())
        .all()
    )


@app.post("/alerts/{alert_id}/resolve", response_model=schemas.AlertOut, tags=["Alerts"])
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    alert = db.query(models.DoctorAlert).filter(models.DoctorAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.doctor_id != doctor.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    alert.is_resolved = True
    db.commit()
    db.refresh(alert)
    return alert


# VISIT ESCALATION  (CHW requests a doctor visit → Doctor accepts & schedules)


@app.post("/patients/{patient_id}/request-visit", response_model=schemas.AlertOut, tags=["Visits"])
def request_visit(
    patient_id: int,
    payload: schemas.VisitEscalateRequest,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """CHW/Doctor escalates a patient to the doctor by requesting a clinic visit.
    Patients can also raise a visit request for themselves, which routes to their CHW."""
    role, user = current
    if role not in ("chw", "doctor", "patient"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="You can only request a visit for yourself")

    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # If the CHW proposed a specific date/time, validate it against the doctor's
    # actual calendar (working hours, lunch, breaks, existing visits) before
    # creating the request — this is what lets a CHW confirm the doctor is
    # actually free instead of blindly firing off a request.
    proposed_date = payload.preferred_date
    if proposed_date:
        ok, err = check_slot_available(db, "doctor", patient.doctor_id, proposed_date, payload.duration_minutes)
        if not ok:
            raise HTTPException(status_code=409, detail=f"Doctor is not available at that time: {err}")

    # Provisional clinic visit, awaiting doctor confirmation — this always
    # lands on the doctor's calendar (the doctor is the one who confirms it).
    visit = models.ClinicVisit(
        patient_id=patient_id,
        scheduled_by=role.upper(),
        scheduled_by_name=user.name,
        provider_role="doctor",
        provider_id=patient.doctor_id,
        visit_type=payload.visit_type,
        visit_date=proposed_date or (datetime.utcnow() + __import__("datetime").timedelta(days=1)),  # provisional
        status="Scheduled",
        reason=payload.reason,
        duration_minutes=payload.duration_minutes,
        doctor_accepted=False,
    )
    db.add(visit)

    alert = models.DoctorAlert(
        patient_id=patient_id,
        doctor_id=patient.doctor_id,
        alert_reason=f"Visit Request ({payload.visit_type}): {payload.reason}",
        doctor_context=f"{role.upper()} {user.name} is requesting a {payload.visit_type.lower()} clinic visit for {patient.name}."
                        + (f" Proposed slot: {proposed_date.strftime('%d %b %Y, %I:%M %p')} (confirmed free on your calendar)." if proposed_date else "")
                        + f" Reason: {payload.reason}",
        # Patient self-requests use a distinct source so they reach the CHW only.
        # Doctors only see "VisitRequest" — i.e. once a CHW has reviewed and escalated it.
        source="PatientVisitRequest" if role == "patient" else "VisitRequest",
        visit_request_status="Requested",
        visit_requested_by=user.name,
    )
    db.add(alert)

    # Notify patient that a visit has been requested (only relevant when CHW/doctor initiates it —
    # a patient's own self-request doesn't need to notify themselves)
    if role != "patient":
        db.add(models.Notification(
            patient_id=patient_id,
            sent_by=role.upper(),
            sent_by_name=user.name,
            message=f"Aapke liye ek {payload.visit_type} clinic visit request ki gayi hai. Doctor ke confirm karne par bataya jaayega.",
            notif_type="visit",
        ))

    db.commit()
    db.refresh(alert)
    return alert


@app.post("/alerts/{alert_id}/accept-visit", response_model=schemas.VisitOut, tags=["Visits"])
def accept_visit(
    alert_id: int,
    payload: schemas.VisitAcceptRequest,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    """Doctor accepts a CHW-requested visit and schedules it. Notifies patient + CHW."""
    alert = db.query(models.DoctorAlert).filter(models.DoctorAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.doctor_id != doctor.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    patient = db.query(models.Patient).filter(models.Patient.id == alert.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Find the provisional clinic visit tied to this request, or create one
    visit = (
        db.query(models.ClinicVisit)
        .filter(models.ClinicVisit.patient_id == alert.patient_id, models.ClinicVisit.doctor_accepted == False)
        .order_by(models.ClinicVisit.created_at.desc())
        .first()
    )
    if not visit:
        visit = models.ClinicVisit(
            patient_id=alert.patient_id,
            scheduled_by="DOCTOR",
            scheduled_by_name=doctor.name,
            visit_type="Mandatory",
            reason=alert.alert_reason,
            provider_role="doctor",
            provider_id=doctor.id,
        )
        db.add(visit)
        db.flush()
    else:
        # Backfill in case this provisional visit predates the provider fields.
        visit.provider_role = "doctor"
        visit.provider_id = doctor.id

    ok, err = check_slot_available(
        db, "doctor", doctor.id, payload.visit_date, payload.duration_minutes,
        exclude_visit_id=visit.id if visit.id else None,
    )
    if not ok:
        raise HTTPException(status_code=409, detail=err)

    visit.visit_date = payload.visit_date
    visit.status = "Scheduled"
    visit.doctor_accepted = True
    visit.chw_notified_acceptance = True
    visit.duration_minutes = payload.duration_minutes
    if payload.notes:
        visit.reason = (visit.reason or "") + f" | Tests: {payload.notes}"
    if visit.visit_type == "Teleconsultation" and payload.meeting_id:
        visit.meeting_id = payload.meeting_id

    alert.visit_request_status = "Accepted"
    alert.is_resolved = True

    # Notify patient
    accept_msg = f"Dr. {doctor.name} ne aapka clinic visit confirm kar diya hai: {payload.visit_date.strftime('%d %b %Y')}."
    if visit.meeting_link:
        accept_msg += f" Join link: {visit.meeting_link}"
    db.add(models.Notification(
        patient_id=alert.patient_id,
        sent_by="Doctor",
        sent_by_name=doctor.name,
        message=accept_msg,
        notif_type="visit_accepted",
    ))

    db.commit()
    db.refresh(visit)
    return visit


# NOTIFICATIONS


@app.post("/notifications", response_model=schemas.NotificationOut, tags=["Notifications"])
def send_notification(
    payload: schemas.NotificationCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    notif = models.Notification(
        patient_id=payload.patient_id,
        sent_by=payload.sent_by,
        sent_by_name=payload.sent_by_name,
        message=payload.message,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


@app.get("/patients/{patient_id}/notifications", response_model=List[schemas.NotificationOut], tags=["Notifications"])
def get_notifications(
    patient_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "dietician":
        raise HTTPException(status_code=403, detail="Dieticians only have access to diet plans, food logs, and exercise plans")
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return (
        db.query(models.Notification)
        .filter(models.Notification.patient_id == patient_id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )


@app.post("/patients/{patient_id}/notifications/read", tags=["Notifications"])
def mark_notifications_read(
    patient_id: int,
    db: Session = Depends(get_db),
    patient: models.Patient = Depends(auth.require_patient),
):
    if patient.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.query(models.Notification).filter(
        models.Notification.patient_id == patient_id,
        models.Notification.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"message": "All notifications marked as read"}



# AI ENDPOINTS


@app.post("/ai/deep-analysis", tags=["AI"])
def deep_analysis(
    payload: schemas.DeepAnalysisRequest,
    db: Session = Depends(get_db),
    doctor: models.Doctor = Depends(auth.require_doctor),
):
    """Doctor asks a deep clinical question about a specific alert."""
    alert = db.query(models.DoctorAlert).filter(models.DoctorAlert.id == payload.alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.doctor_id != doctor.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    patient = db.query(models.Patient).filter(models.Patient.id == alert.patient_id).first()
    recent = (
        db.query(models.DailyLog)
        .filter(models.DailyLog.patient_id == alert.patient_id)
        .order_by(models.DailyLog.created_at.desc())
        .limit(7)
        .all()
    )

    result = ai_service.deep_doctor_analysis(
        doctor_question=payload.question,
        patient_name=patient.name if patient else "Unknown",
        patient_age=patient.age or 0 if patient else 0,
        condition=patient.condition or "Type 2 Diabetes" if patient else "Type 2 Diabetes",
        alert_reason=alert.alert_reason or "",
        recent_logs=[_log_to_dict(l) for l in recent],
    )
    return result


@app.post("/ai/trend-check/{patient_id}", tags=["AI"])
def trigger_trend_check(
    patient_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """Manually trigger an AI trend check for a patient. Doctor or CHW only."""
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")

    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    logs = (
        db.query(models.DailyLog)
        .filter(models.DailyLog.patient_id == patient_id)
        .order_by(models.DailyLog.created_at.desc())
        .limit(7)
        .all()
    )
    rx = (
        db.query(models.Prescription)
        .filter(models.Prescription.patient_id == patient_id, models.Prescription.active == True)
        .first()
    )
    rx_dict = {
        "medication_name": rx.medication_name,
        "dosage": rx.dosage,
        "instructions": rx.instructions,
    } if rx else None

    result = ai_service.generate_trend_alert(
        patient_name=patient.name,
        patient_age=patient.age or 0,
        gender=patient.gender or "Unknown",
        condition=patient.condition or "Type 2 Diabetes",
        logs=[_log_to_dict(l) for l in logs],
        prescription=rx_dict,
    )

    if result.get("should_alert"):
        alert = models.DoctorAlert(
            patient_id=patient_id,
            doctor_id=patient.doctor_id,
            alert_reason=result.get("alert_reason", "Trend alert"),
            doctor_context=result.get("doctor_context"),
            source="AutoTrend",
        )
        db.add(alert)
        db.commit()
        return {"alert_created": True, **result}

    return {"alert_created": False, **result}



# CHW PRESCRIPTION SUGGESTION


@app.post("/patients/{patient_id}/suggest-prescription", tags=["CHW"])
def suggest_prescription(
    patient_id: int,
    medication_name: str = Body(...),
    dosage: str = Body(...),
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role != "chw":
        raise HTTPException(status_code=403, detail="CHW only")

    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    alert = models.DoctorAlert(
        patient_id=patient_id,
        doctor_id=patient.doctor_id,
        alert_reason=f"CHW prescription suggestion: {medication_name} — {dosage}",
        doctor_context=(
            f"CHW {user.name} suggests reviewing a prescription change for {patient.name}: "
            f"{medication_name}, {dosage}. Please review patient history and confirm or modify."
        ),
        source="CHW",
    )
    db.add(alert)
    db.commit()
    return {"message": "Prescription suggestion sent to doctor"}


# RAW AI PROXY  (called directly by index.html's callAI function)


class RawAIRequest(BaseModel):
    prompt: str

@app.post("/ai/raw", tags=["AI"])
def raw_ai(payload: RawAIRequest, doctor: models.Doctor = Depends(auth.require_doctor)):
    """Proxy raw AI calls from the frontend so the API key stays on the server.
    Restricted strictly to Doctor role only."""
    try:
        return ai_service._call(payload.prompt)
    except Exception as e:
        return {"error": str(e)}



# ---------------------------------------------------------------------------
# SCHEDULING ENGINE
#
# Every *provider* — the doctor, or each individual CHW — has their own
# working schedule (DoctorSettings / ChwSettings): working hours, a lunch
# window, a slot size (default 30 min) and working days, plus one-off
# DoctorBreak/ChwBreak rows for ad-hoc blocked time. A slot is available only
# if it's inside working hours, outside lunch, outside any break, and not
# already covered by another non-cancelled visit *on that same provider's
# calendar*. Multiple CHWs under one doctor each get their own independent
# calendar — never shared with each other or with the doctor. This logic is
# shared by the calendar view and by every endpoint that creates/accepts/
# moves a visit.
# ---------------------------------------------------------------------------

from datetime import timedelta


def _time_to_minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _minutes_to_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def get_or_create_provider_settings(db: Session, provider_role: str, provider_id: int):
    """Returns the DoctorSettings or ChwSettings row for this provider, creating
    a default one if it doesn't exist yet. Each CHW's row is independent."""
    if provider_role == "chw":
        settings = db.query(models.ChwSettings).filter(models.ChwSettings.chw_id == provider_id).first()
        if not settings:
            settings = models.ChwSettings(chw_id=provider_id)
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings
    settings = db.query(models.DoctorSettings).filter(models.DoctorSettings.doctor_id == provider_id).first()
    if not settings:
        settings = models.DoctorSettings(doctor_id=provider_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def _provider_break_query(db: Session, provider_role: str, provider_id: int, date_str: str):
    if provider_role == "chw":
        return db.query(models.ChwBreak).filter(
            models.ChwBreak.chw_id == provider_id, models.ChwBreak.date == date_str
        )
    return db.query(models.DoctorBreak).filter(
        models.DoctorBreak.doctor_id == provider_id, models.DoctorBreak.date == date_str
    )


def check_slot_available(db: Session, provider_role: str, provider_id: int, visit_dt: datetime,
                          duration_minutes: int, exclude_visit_id: Optional[int] = None):
    """Returns (ok: bool, error_message: Optional[str])."""
    who = "Doctor" if provider_role != "chw" else "CHW"
    settings = get_or_create_provider_settings(db, provider_role, provider_id)
    weekday = visit_dt.weekday()
    if weekday not in (settings.working_days or []):
        return False, f"{who} is not working on this day."

    start = _time_to_minutes(settings.working_start)
    end = _time_to_minutes(settings.working_end)
    lunch_start = _time_to_minutes(settings.lunch_start)
    lunch_end = _time_to_minutes(settings.lunch_end)
    req_start = visit_dt.hour * 60 + visit_dt.minute
    req_end = req_start + duration_minutes

    if req_start < start or req_end > end:
        return False, f"{who}'s working hours are {settings.working_start}-{settings.working_end}."

    if req_start < lunch_end and req_end > lunch_start:
        return False, f"{who} is on Lunch Break ({settings.lunch_start}-{settings.lunch_end})."

    date_str = visit_dt.strftime("%Y-%m-%d")
    breaks = _provider_break_query(db, provider_role, provider_id, date_str).all()
    for b in breaks:
        b_start = _time_to_minutes(b.start_time)
        b_end = _time_to_minutes(b.end_time)
        if req_start < b_end and req_end > b_start:
            return False, f"{who} has a blocked period ({b.reason}) at this time."

    day_start_dt = datetime.combine(visit_dt.date(), datetime.min.time())
    day_end_dt = day_start_dt + timedelta(days=1)
    q = db.query(models.ClinicVisit).filter(
        models.ClinicVisit.provider_role == provider_role,
        models.ClinicVisit.provider_id == provider_id,
        models.ClinicVisit.visit_date >= day_start_dt,
        models.ClinicVisit.visit_date < day_end_dt,
        models.ClinicVisit.status != "Cancelled",
    )
    if exclude_visit_id:
        q = q.filter(models.ClinicVisit.id != exclude_visit_id)
    for v in q.all():
        if not v.visit_date:
            continue
        v_start = v.visit_date.hour * 60 + v.visit_date.minute
        v_end = v_start + (v.duration_minutes or 30)
        if req_start < v_end and req_end > v_start:
            return False, f"{who} already has an appointment at this time."

    return True, None


def build_calendar_day(db: Session, provider_role: str, provider_id: int, day, owner_name: str = None,
                        editable: bool = False) -> schemas.CalendarDayOut:
    settings = get_or_create_provider_settings(db, provider_role, provider_id)
    date_str = day.strftime("%Y-%m-%d")
    weekday = day.weekday()
    slot_min = settings.slot_minutes or 30

    if weekday not in (settings.working_days or []):
        return schemas.CalendarDayOut(date=date_str, slot_minutes=slot_min, slots=[],
                                       owner_role=provider_role, owner_name=owner_name, editable=editable)

    start = _time_to_minutes(settings.working_start)
    end = _time_to_minutes(settings.working_end)
    lunch_start = _time_to_minutes(settings.lunch_start)
    lunch_end = _time_to_minutes(settings.lunch_end)

    day_start_dt = datetime.combine(day, datetime.min.time())
    day_end_dt = day_start_dt + timedelta(days=1)
    visits = (
        db.query(models.ClinicVisit)
        .filter(
            models.ClinicVisit.provider_role == provider_role,
            models.ClinicVisit.provider_id == provider_id,
            models.ClinicVisit.visit_date >= day_start_dt,
            models.ClinicVisit.visit_date < day_end_dt,
            models.ClinicVisit.status != "Cancelled",
        )
        .all()
    )
    breaks = _provider_break_query(db, provider_role, provider_id, date_str).all()

    slots: List[schemas.CalendarSlot] = []
    t = start
    while t < end:
        status_, label, visit_id, patient_id, patient_name, visit_type, break_id, reason = (
            "available", None, None, None, None, None, None, None
        )

        if lunch_start <= t < lunch_end:
            status_, label = "lunch", "Lunch Break"
        else:
            for b in breaks:
                if _time_to_minutes(b.start_time) <= t < _time_to_minutes(b.end_time):
                    status_, label, break_id, reason = "blocked", b.reason, b.id, b.reason
                    break
            if status_ == "available":
                for v in visits:
                    if not v.visit_date:
                        continue
                    v_start = v.visit_date.hour * 60 + v.visit_date.minute
                    v_dur = v.duration_minutes or 30
                    if v_start <= t < v_start + v_dur:
                        patient = db.query(models.Patient).filter(models.Patient.id == v.patient_id).first()
                        patient_name = patient.name if patient else None
                        status_, label = "booked", patient_name
                        visit_id, patient_id, visit_type = v.id, v.patient_id, v.visit_type
                        break

        slots.append(schemas.CalendarSlot(
            time=_minutes_to_time(t), status=status_, label=label, visit_id=visit_id,
            patient_id=patient_id, patient_name=patient_name, visit_type=visit_type,
            break_id=break_id, reason=reason,
        ))
        t += slot_min

    return schemas.CalendarDayOut(date=date_str, slot_minutes=slot_min, slots=slots,
                                   owner_role=provider_role, owner_name=owner_name, editable=editable)


# ── Doctor working hours / lunch / slot size ────────────────────────────────

@app.get("/doctors/me/settings", response_model=schemas.DoctorSettingsOut, tags=["Calendar"])
def get_my_doctor_settings(doctor: models.Doctor = Depends(auth.require_doctor), db: Session = Depends(get_db)):
    return get_or_create_provider_settings(db, "doctor", doctor.id)


@app.put("/doctors/me/settings", response_model=schemas.DoctorSettingsOut, tags=["Calendar"])
def update_my_doctor_settings(
    payload: schemas.DoctorSettingsUpdate,
    doctor: models.Doctor = Depends(auth.require_doctor),
    db: Session = Depends(get_db),
):
    settings = get_or_create_provider_settings(db, "doctor", doctor.id)
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings


# ── Dynamic breaks (block time) — doctor ────────────────────────────────────

@app.post("/doctors/me/breaks", response_model=schemas.DoctorBreakOut, tags=["Calendar"])
def create_doctor_break(
    payload: schemas.DoctorBreakCreate,
    doctor: models.Doctor = Depends(auth.require_doctor),
    db: Session = Depends(get_db),
):
    brk = models.DoctorBreak(doctor_id=doctor.id, **payload.dict())
    db.add(brk)
    db.commit()
    db.refresh(brk)
    return brk


@app.get("/doctors/me/breaks", response_model=List[schemas.DoctorBreakOut], tags=["Calendar"])
def list_doctor_breaks(
    date: Optional[str] = None,
    doctor: models.Doctor = Depends(auth.require_doctor),
    db: Session = Depends(get_db),
):
    q = db.query(models.DoctorBreak).filter(models.DoctorBreak.doctor_id == doctor.id)
    if date:
        q = q.filter(models.DoctorBreak.date == date)
    return q.all()


@app.delete("/doctors/me/breaks/{break_id}", tags=["Calendar"])
def delete_doctor_break(
    break_id: int,
    doctor: models.Doctor = Depends(auth.require_doctor),
    db: Session = Depends(get_db),
):
    brk = db.query(models.DoctorBreak).filter(models.DoctorBreak.id == break_id).first()
    if not brk or brk.doctor_id != doctor.id:
        raise HTTPException(status_code=404, detail="Break not found")
    db.delete(brk)
    db.commit()
    return {"ok": True}


# ── CHW working hours / lunch / slot size — each CHW's own, independent ────

@app.get("/chws/me/settings", response_model=schemas.ChwSettingsOut, tags=["Calendar"])
def get_my_chw_settings(current=Depends(auth.get_current_user), db: Session = Depends(get_db)):
    role, user = current
    if role != "chw":
        raise HTTPException(status_code=403, detail="CHW only")
    return get_or_create_provider_settings(db, "chw", user.id)


@app.put("/chws/me/settings", response_model=schemas.ChwSettingsOut, tags=["Calendar"])
def update_my_chw_settings(
    payload: schemas.ChwSettingsUpdate,
    current=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    role, user = current
    if role != "chw":
        raise HTTPException(status_code=403, detail="CHW only")
    settings = get_or_create_provider_settings(db, "chw", user.id)
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(settings, key, value)
    db.commit()
    db.refresh(settings)
    return settings


# ── Dynamic breaks (block time) — CHW's own calendar ────────────────────────

@app.post("/chws/me/breaks", response_model=schemas.ChwBreakOut, tags=["Calendar"])
def create_chw_break(
    payload: schemas.ChwBreakCreate,
    current=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    role, user = current
    if role != "chw":
        raise HTTPException(status_code=403, detail="CHW only")
    brk = models.ChwBreak(chw_id=user.id, **payload.dict())
    db.add(brk)
    db.commit()
    db.refresh(brk)
    return brk


@app.get("/chws/me/breaks", response_model=List[schemas.ChwBreakOut], tags=["Calendar"])
def list_chw_breaks(
    date: Optional[str] = None,
    current=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    role, user = current
    if role != "chw":
        raise HTTPException(status_code=403, detail="CHW only")
    q = db.query(models.ChwBreak).filter(models.ChwBreak.chw_id == user.id)
    if date:
        q = q.filter(models.ChwBreak.date == date)
    return q.all()


@app.delete("/chws/me/breaks/{break_id}", tags=["Calendar"])
def delete_chw_break(
    break_id: int,
    current=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    role, user = current
    if role != "chw":
        raise HTTPException(status_code=403, detail="CHW only")
    brk = db.query(models.ChwBreak).filter(models.ChwBreak.id == break_id).first()
    if not brk or brk.chw_id != user.id:
        raise HTTPException(status_code=404, detail="Break not found")
    db.delete(brk)
    db.commit()
    return {"ok": True}


# ── Calendar day view (available / booked / lunch / blocked slots) ─────────

@app.get("/calendar/{date}", response_model=schemas.CalendarDayOut, tags=["Calendar"])
def get_calendar_day(
    date: str,
    view: Optional[str] = None,   # CHW only: pass view=doctor to peek at the doctor's calendar (read-only)
    current=Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """date is 'YYYY-MM-DD'.
    - Doctor: always sees their own calendar (editable).
    - CHW: by default sees their OWN calendar (editable — it's their own patient
      visits). Pass ?view=doctor to instead see their supervising doctor's
      calendar, strictly read-only, e.g. to pick a free slot before requesting
      a doctor visit. Each CHW's own calendar is completely independent of
      every other CHW's — nothing here is ever shared between them.
    """
    role, user = current
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    if role == "doctor":
        return build_calendar_day(db, "doctor", user.id, day, owner_name=user.name, editable=True)

    if role == "chw":
        if view == "doctor":
            doctor = db.query(models.Doctor).filter(models.Doctor.id == user.doctor_id).first()
            return build_calendar_day(db, "doctor", user.doctor_id, day,
                                       owner_name=(doctor.name if doctor else None), editable=False)
        return build_calendar_day(db, "chw", user.id, day, owner_name=user.name, editable=True)

    raise HTTPException(status_code=403, detail="Only doctors and CHWs can view a calendar")


# CLINIC VISITS


@app.post("/visits", response_model=schemas.VisitOut, tags=["Visits"])
def create_visit(payload: schemas.VisitCreate, db: Session = Depends(get_db), current=Depends(auth.get_current_user)):
    role, user = current
    # Doctor and CHW can each directly create a *confirmed* visit — it locks
    # the slot on THEIR OWN calendar and immediately tells the patient it's
    # scheduled. A CHW booking here is a home visit on the CHW's own
    # independent calendar; it never touches the doctor's calendar. To
    # request time on the doctor's calendar instead, use
    # POST /patients/{id}/request-visit, which leaves the doctor to confirm.
    if role not in ("doctor", "chw"):
        raise HTTPException(status_code=403, detail="Only the doctor or a CHW can directly schedule a confirmed visit. Use 'Request Doctor Visit' instead.")
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    provider_role = "doctor" if role == "doctor" else "chw"
    provider_id = user.id

    ok, err = check_slot_available(db, provider_role, provider_id, payload.visit_date, payload.duration_minutes)
    if not ok:
        raise HTTPException(status_code=409, detail=err)

    visit = models.ClinicVisit(
        patient_id=payload.patient_id, scheduled_by=role.upper(),
        scheduled_by_name=user.name, visit_type=payload.visit_type,
        visit_date=payload.visit_date, reason=payload.reason, status="Scheduled",
        duration_minutes=payload.duration_minutes,
        meeting_id=payload.meeting_id if payload.visit_type == "Teleconsultation" else None,
        provider_role=provider_role, provider_id=provider_id,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)

    visit_msg = f"Aapka {payload.visit_type} clinic visit schedule ho gaya hai: {payload.visit_date.strftime('%d %b %Y, %I:%M %p')}."
    if visit.meeting_link:
        visit_msg += f" Join link: {visit.meeting_link}"
    db.add(models.Notification(
        patient_id=payload.patient_id,
        sent_by=role.upper(), sent_by_name=user.name,
        message=visit_msg,
        notif_type="visit",
    ))
    if role == "doctor":
        db.add(models.Notification(
            patient_id=payload.patient_id, sent_by="System", sent_by_name="MetaCare",
            message=f"CHW ko bhi is visit ki jaankari de di gayi hai.", notif_type="visit",
        ))
    db.commit()
    return visit


@app.post("/visits/{visit_id}/follow-up", response_model=schemas.VisitOut, tags=["Visits"])
def schedule_follow_up(
    visit_id: int,
    payload: schemas.FollowUpCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """Quick 'Schedule Follow-up' action off an existing visit — e.g. one week later."""
    role, user = current
    # Same rule as POST /visits — this creates a confirmed booking, so only
    # the doctor or a CHW can do it directly, each on their own calendar.
    if role not in ("doctor", "chw"):
        raise HTTPException(status_code=403, detail="Only the doctor or a CHW can directly schedule a confirmed follow-up.")
    source = db.query(models.ClinicVisit).filter(models.ClinicVisit.id == visit_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Visit not found")
    patient = db.query(models.Patient).filter(models.Patient.id == source.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    provider_role = "doctor" if role == "doctor" else "chw"
    provider_id = user.id

    base_date = (source.visit_date or datetime.utcnow()) + timedelta(days=payload.offset_days)
    if payload.visit_time:
        hh, mm = payload.visit_time.split(":")
        base_date = base_date.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)

    ok, err = check_slot_available(db, provider_role, provider_id, base_date, payload.duration_minutes)
    if not ok:
        raise HTTPException(status_code=409, detail=err)

    visit = models.ClinicVisit(
        patient_id=patient.id, scheduled_by=role.upper(), scheduled_by_name=user.name,
        visit_type=payload.visit_type, visit_date=base_date,
        reason=payload.reason or f"Follow-up to visit #{source.id}",
        status="Scheduled", duration_minutes=payload.duration_minutes,
        meeting_id=payload.meeting_id if payload.visit_type == "Teleconsultation" else None,
        provider_role=provider_role, provider_id=provider_id,
    )
    db.add(visit)
    db.flush()

    followup_msg = f"Follow-up visit schedule ho gaya hai: {base_date.strftime('%d %b %Y, %I:%M %p')}."
    if visit.meeting_link:
        followup_msg += f" Join link: {visit.meeting_link}"
    db.add(models.Notification(
        patient_id=patient.id, sent_by=role.upper(), sent_by_name=user.name,
        message=followup_msg,
        notif_type="visit",
    ))
    db.commit()
    db.refresh(visit)
    return visit


@app.get("/patients/{patient_id}/visits", response_model=List[schemas.VisitOut], tags=["Visits"])
def get_patient_visits(
    patient_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "dietician":
        raise HTTPException(status_code=403, detail="Dieticians only have access to diet plans, food logs, and exercise plans")
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return db.query(models.ClinicVisit).filter(models.ClinicVisit.patient_id == patient_id).all()


@app.put("/visits/{visit_id}", response_model=schemas.VisitOut, tags=["Visits"])
def update_visit(
    visit_id: int,
    payload: schemas.VisitUpdate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    visit = db.query(models.ClinicVisit).filter(models.ClinicVisit.id == visit_id).first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    patient = db.query(models.Patient).filter(models.Patient.id == visit.patient_id).first()
    if role == "chw" and (not patient or patient.chw_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and (not patient or patient.doctor_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    update_data = payload.dict(exclude_unset=True)

    # --- SCHEDULING VALIDATION FOR RESCHEDULING ---
    new_date = update_data.get("visit_date", visit.visit_date)
    new_duration = update_data.get("duration_minutes", visit.duration_minutes or 30)

    if "visit_date" in update_data or "duration_minutes" in update_data:
        if new_date:  # don't pass None to the validator
            ok, err = check_slot_available(
                db,
                visit.provider_role or "doctor",
                visit.provider_id or patient.doctor_id,
                new_date,
                new_duration,
                exclude_visit_id=visit.id,  # visit doesn't conflict with its own old slot
            )
            if not ok:
                raise HTTPException(status_code=409, detail=err)

    if "meeting_id" in update_data and visit.visit_type != "Teleconsultation":
        update_data.pop("meeting_id")  # meeting IDs only apply to Teleconsultation visits

    for key, value in update_data.items():
        setattr(visit, key, value)
    db.commit()
    db.refresh(visit)
    return visit



# DIET PLANS
#
# All diet content is grounded in the MetaLife T2DM Nutrition Therapy Guide
# (RSSDI 2017 / ICMR-NIN 2024 / ADA / Asian-Indian BMI cutoffs / DiRECT
# Trial) — see diet_reference.py. Plans are organised into 4 BMI groups.


@app.get("/diet-reference/groups", tags=["Diet"])
def list_diet_reference_groups(current=Depends(auth.require_diet_access)):
    """Slim list of the 4 clinical BMI groups — for Doctor/CHW/Dietician to
    pick from, or to show alongside a patient's current plan."""
    return {
        "groups": [diet_reference.group_summary(n) for n in range(1, 5)],
        "clinical_notes": diet_reference.CLINICAL_NOTES,
    }


@app.get("/diet-reference/groups/{group_no}", tags=["Diet"])
def get_diet_reference_group(group_no: int, current=Depends(auth.require_diet_access)):
    """Full bilingual clinical detail for one BMI group: meal times, macros,
    recommended/avoid foods, strict avoidance, special advice."""
    group = diet_reference.BMI_GROUPS.get(group_no)
    if not group:
        raise HTTPException(status_code=404, detail="BMI group must be 1-4")
    return group


@app.get("/diet-reference/substitutions", tags=["Diet"])
def get_diet_substitutions(current=Depends(auth.require_diet_access)):
    """Master bilingual food-substitution table and GI chart — applies to all groups."""
    return {"substitutions": diet_reference.MASTER_SUBSTITUTIONS, "gi_chart": diet_reference.GI_CHART}


@app.post("/patients/{patient_id}/diet-plans/generate", response_model=schemas.DietPlanOut, tags=["Diet"])
def generate_diet_plan_for_patient(
    patient_id: int,
    payload: schemas.DietPlanGenerateRequest,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """Auto-generate a clinically-grounded bilingual diet plan for a patient,
    using their weight/height to pick the correct Asian-Indian BMI group
    (Doctor, CHW, or Dietician can override the group manually)."""
    role, user = current
    if role not in ("chw", "doctor", "dietician"):
        raise HTTPException(status_code=403, detail="CHW, Dietician, or Doctor only")
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    recent = (
        db.query(models.DailyLog)
        .filter(models.DailyLog.patient_id == patient_id)
        .order_by(models.DailyLog.created_at.desc())
        .limit(7)
        .all()
    )
    prescription = (
        db.query(models.Prescription)
        .filter(models.Prescription.patient_id == patient_id, models.Prescription.active == True)
        .first()
    )

    result = ai_service.generate_diet_plan(
        patient_name=patient.name,
        patient_age=patient.age,
        gender=patient.gender,
        condition=patient.condition,
        hba1c=patient.hba1c,
        weight=patient.weight,
        height_cm=patient.height_cm,
        recent_logs=[_log_to_dict(l) for l in recent],
        prescription={"medication_name": prescription.medication_name, "dosage": prescription.dosage} if prescription else None,
        additional_notes=payload.additional_notes or "",
        bmi_group_override=payload.bmi_group_override,
    )
    result.pop("error", None)

    db.query(models.DietPlan).filter(models.DietPlan.patient_id == patient_id).update({"active": False})
    plan = models.DietPlan(
        patient_id=patient_id,
        created_by=role.upper(),
        created_by_name=user.name,
        **{k: v for k, v in result.items() if k in schemas.DietPlanCreate.model_fields},
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@app.post("/diet-plans", response_model=schemas.DietPlanOut, tags=["Diet"])
def create_diet_plan(
    payload: schemas.DietPlanCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor", "dietician"):
        raise HTTPException(status_code=403, detail="CHW, Dietician, or Doctor only")
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.query(models.DietPlan).filter(models.DietPlan.patient_id == payload.patient_id).update({"active": False})
    plan = models.DietPlan(
        **payload.dict(),
        created_by=role.upper(),
        created_by_name=user.name,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@app.get("/patients/{patient_id}/diet-plans", response_model=List[schemas.DietPlanOut], tags=["Diet"])
def get_diet_plans(
    patient_id: int,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    q = db.query(models.DietPlan).filter(models.DietPlan.patient_id == patient_id)
    if active_only:
        q = q.filter(models.DietPlan.active == True)
    return q.all()


@app.put("/diet-plans/{plan_id}", response_model=schemas.DietPlanOut, tags=["Diet"])
def update_diet_plan(
    plan_id: int,
    payload: schemas.DietPlanUpdate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    """Partial update to an existing diet plan — e.g. CHW or Doctor sets calorie/protein targets
    without overwriting the rest of the plan."""
    role, user = current
    if role not in ("chw", "doctor", "dietician"):
        raise HTTPException(status_code=403, detail="CHW, Dietician, or Doctor only")
    plan = db.query(models.DietPlan).filter(models.DietPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Diet plan not found")
    patient = db.query(models.Patient).filter(models.Patient.id == plan.patient_id).first()
    if role == "chw" and (not patient or patient.chw_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and (not patient or patient.doctor_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and (not patient or patient.dietician_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(plan, key, value)
    db.commit()
    db.refresh(plan)
    return plan


# EXERCISE RECOMMENDATIONS  (simple text field on Patient — Doctor sets, CHW can also edit)


@app.put("/patients/{patient_id}/exercise", response_model=schemas.PatientOut, tags=["Exercise"])
def update_exercise_plan(
    patient_id: int,
    payload: schemas.ExerciseUpdate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor", "dietician"):
        raise HTTPException(status_code=403, detail="CHW, Dietician, or Doctor only")
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    patient.exercise_plan = payload.exercise_plan
    patient.exercise_updated_by = role.upper()
    patient.exercise_updated_by_name = user.name
    patient.exercise_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(patient)
    return patient


# FOOD LOG  (simple patient food diary — calories & protein)


@app.post("/patients/{patient_id}/food-logs", response_model=schemas.FoodLogOut, tags=["Diet"])
def add_food_log(
    patient_id: int,
    payload: schemas.FoodLogCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role in ("chw", "doctor", "dietician"):
        patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        if role == "chw" and patient.chw_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if role == "doctor" and patient.doctor_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if role == "dietician" and patient.dietician_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    log = models.FoodLog(
        patient_id=patient_id,
        food_name=payload.food_name,
        calories=payload.calories,
        protein=payload.protein,
        logged_by="Patient" if role == "patient" else role.upper(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get("/patients/{patient_id}/food-logs", response_model=List[schemas.FoodLogOut], tags=["Diet"])
def get_food_logs(
    patient_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return (
        db.query(models.FoodLog)
        .filter(models.FoodLog.patient_id == patient_id)
        .order_by(models.FoodLog.created_at.desc())
        .limit(limit)
        .all()
    )


# EXERCISE LOG  (simple patient daily check-in — did they do the exercise or not)


@app.post("/patients/{patient_id}/exercise-logs", response_model=schemas.ExerciseLogOut, tags=["Exercise"])
def add_exercise_log(
    patient_id: int,
    payload: schemas.ExerciseLogCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role in ("chw", "doctor", "dietician"):
        patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        if role == "chw" and patient.chw_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if role == "doctor" and patient.doctor_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        if role == "dietician" and patient.dietician_id != user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
    log = models.ExerciseLog(
        patient_id=patient_id,
        completed=payload.completed,
        notes=payload.notes,
        logged_by="Patient" if role == "patient" else role.upper(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get("/patients/{patient_id}/exercise-logs", response_model=List[schemas.ExerciseLogOut], tags=["Exercise"])
def get_exercise_logs(
    patient_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return (
        db.query(models.ExerciseLog)
        .filter(models.ExerciseLog.patient_id == patient_id)
        .order_by(models.ExerciseLog.created_at.desc())
        .limit(limit)
        .all()
    )



# LAB TESTS


@app.post("/lab-tests", response_model=schemas.LabTestOut, tags=["Tests"])
def order_lab_test(
    payload: schemas.LabTestCreate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    patient = db.query(models.Patient).filter(models.Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    test = models.LabTest(
        **payload.dict(),
        ordered_by=role.upper(),
        ordered_by_name=user.name,
    )
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


@app.get("/patients/{patient_id}/lab-tests", response_model=List[schemas.LabTestOut], tags=["Tests"])
def get_lab_tests(
    patient_id: int,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if role == "patient" and user.id != patient_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "chw" and patient.chw_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and patient.doctor_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "dietician" and patient.dietician_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return db.query(models.LabTest).filter(models.LabTest.patient_id == patient_id).all()


@app.put("/lab-tests/{test_id}", response_model=schemas.LabTestOut, tags=["Tests"])
def update_lab_test(
    test_id: int,
    payload: schemas.LabTestUpdate,
    db: Session = Depends(get_db),
    current=Depends(auth.get_current_user),
):
    role, user = current
    if role not in ("chw", "doctor"):
        raise HTTPException(status_code=403, detail="CHW or Doctor only")
    test = db.query(models.LabTest).filter(models.LabTest.id == test_id).first()
    if not test:
        raise HTTPException(status_code=404, detail="Lab test not found")
    patient = db.query(models.Patient).filter(models.Patient.id == test.patient_id).first()
    if role == "chw" and (not patient or patient.chw_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "doctor" and (not patient or patient.doctor_id != user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    for key, value in payload.dict(exclude_unset=True).items():
        setattr(test, key, value)
    db.commit()
    db.refresh(test)
    return test

# Sentry check
# @app.get("/sentry-debug")
# async def trigger_error():
#     return 1 / 0

# HEALTH CHECK


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "app": "MetaCare API v1.0"}

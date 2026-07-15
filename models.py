from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    specialization = Column(String)
    hospital = Column(String)
    phone = Column(String)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    patients = relationship("Patient", back_populates="doctor")
    chws = relationship("CHW", back_populates="doctor")
    dieticians = relationship("Dietician", back_populates="doctor")
    alerts = relationship("DoctorAlert", back_populates="doctor")


class CHW(Base):
    __tablename__ = "chws"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    area = Column(String)
    phone = Column(String)
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="chws")
    patients = relationship("Patient", back_populates="chw")
    tasks = relationship("CHWTask", back_populates="chw")


class Dietician(Base):
    """A Dietician is a restricted CHW-like role. A patient can be assigned to a
    CHW AND a Dietician at the same time. The Dietician can only view/manage the
    patient's diet plans, food logs, and exercise plan — nothing else."""
    __tablename__ = "dieticians"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    specialization = Column(String)          # e.g. "Diabetic Nutrition"
    phone = Column(String)
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    doctor = relationship("Doctor", back_populates="dieticians")
    patients = relationship("Patient", back_populates="dietician")


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    gender = Column(String)
    phone = Column(String)
    village = Column(String)
    condition = Column(String, default="Type 2 Diabetes")
    hba1c = Column(Float)
    weight = Column(Float)
    height_cm = Column(Float)   # used to compute Asian-Indian BMI for diet grouping
    chw_id = Column(Integer, ForeignKey("chws.id"))
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    dietician_id = Column(Integer, ForeignKey("dieticians.id"), nullable=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── Terms & Conditions consent (given by the patient) ──────────────────
    consent_given = Column(Boolean, default=False)
    consent_given_at = Column(DateTime, nullable=True)
    consent_version = Column(String, nullable=True)   # which T&C text version they agreed to

    # ── Extended "Add Patient" form fields ─────────────────────────────────
    title = Column(String)                  # Mr / Mrs / Dr etc
    dob = Column(DateTime)
    existing_id = Column(String)            # "Existing ID" field
    blood_group = Column(String)
    preferred_language = Column(String)
    email = Column(String)
    address = Column(Text)
    city = Column(String)
    area_pin = Column(String)
    referred_by_name = Column(String)
    referred_by_specialization = Column(String)
    channel = Column(String)
    care_of = Column(String)                # C/O
    occupation = Column(String)
    phone2 = Column(String)                 # Mobile 2
    tag = Column(String)

    # ── Simple exercise recommendation (set by Doctor, editable by CHW too) ──
    exercise_plan = Column(Text)
    exercise_updated_by = Column(String)        # Doctor | CHW
    exercise_updated_by_name = Column(String)
    exercise_updated_at = Column(DateTime)

    chw = relationship("CHW", back_populates="patients")
    dietician = relationship("Dietician", back_populates="patients")
    doctor = relationship("Doctor", back_populates="patients")
    logs = relationship("DailyLog", back_populates="patient", order_by="DailyLog.created_at.desc()")
    prescriptions = relationship("Prescription", back_populates="patient")
    tasks = relationship("CHWTask", back_populates="patient")
    alerts = relationship("DoctorAlert", back_populates="patient")
    notifications = relationship("Notification", back_populates="patient")
    events = relationship("PatientEvent", back_populates="patient")
    clinic_visits = relationship("ClinicVisit", back_populates="patient",
                                 order_by="ClinicVisit.visit_date.desc()")
    diet_plans = relationship("DietPlan", back_populates="patient",
                              order_by="DietPlan.created_at.desc()")
    lab_tests = relationship("LabTest", back_populates="patient",
                             order_by="LabTest.scheduled_date.desc()")
    food_logs = relationship("FoodLog", back_populates="patient",
                             order_by="FoodLog.created_at.desc()")
    exercise_logs = relationship("ExerciseLog", back_populates="patient",
                                 order_by="ExerciseLog.created_at.desc()")
    documents = relationship("PatientDocument", back_populates="patient",
                             order_by="PatientDocument.created_at.desc()")


class DailyLog(Base):
    __tablename__ = "daily_logs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    blood_sugar = Column(Float)
    medication_taken = Column(Boolean)
    weight = Column(Float)
    raw_text = Column(Text)
    logged_by = Column(String, default="Patient")
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="logs")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    medication_name = Column(String, nullable=False)
    dosage = Column(String)
    instructions = Column(Text)
    suggested_by = Column(String, default="Doctor")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="prescriptions")


class CHWTask(Base):
    __tablename__ = "chw_tasks"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    chw_id = Column(Integer, ForeignKey("chws.id"))
    task_type = Column(String, default="Patient Report")
    status = Column(String, default="Pending")          # Pending | Resolved | Escalated
    raw_patient_text = Column(Text)
    ai_summary = Column(Text)
    ai_classification = Column(String)                  # Routine | Needs Follow Up | Emergency
    extracted_symptoms = Column(JSON, default=[])
    chw_validated = Column(Boolean, default=False)
    chw_validated_note = Column(Text)
    ai_doctor_context = Column(Text)
    ai_suggested_action = Column(Text)
    # Diet plan validation fields
    diet_plan_validated = Column(Boolean, default=False)
    diet_plan_chw_note = Column(Text)
    # Simple non-AI sugar threshold check (<70 or >250 mg/dL)
    critical_sugar_alert = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="tasks")
    chw = relationship("CHW", back_populates="tasks")


class DoctorAlert(Base):
    __tablename__ = "doctor_alerts"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    alert_reason = Column(Text)
    doctor_context = Column(Text)
    source = Column(String)         # AutoTrend | System | CHW | VisitRequest
    is_resolved = Column(Boolean, default=False)
    # Visit escalation flow
    visit_request_status = Column(String)               # Requested | Accepted | Declined
    visit_requested_by = Column(String)                 # CHW name
    chw_acknowledged = Column(Boolean, default=False)    # CHW has seen & cleared the doctor's response (Accepted/Declined) from their queue
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="alerts")
    doctor = relationship("Doctor", back_populates="alerts")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    sent_by = Column(String)        # CHW | Doctor | System
    sent_by_name = Column(String)
    message = Column(Text)
    notif_type = Column(String, default="message")   # message | visit | diet | test | visit_accepted
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="notifications")


class PatientEvent(Base):
    __tablename__ = "patient_events"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    event_type = Column(String)     # DAILY_LOG | PATIENT_REPORT | ESCALATION | VISIT | DIET | TEST
    payload = Column(JSON)
    source = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="events")


# ─── NEW MODELS ───────────────────────────────────────────────────────────────

class ClinicVisit(Base):
    """Tracks both mandatory (scheduled) and impromptu clinic visits."""
    __tablename__ = "clinic_visits"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    scheduled_by = Column(String)           # CHW | DOCTOR
    scheduled_by_name = Column(String)
    visit_type = Column(String, default="Mandatory")    # Mandatory | Impromptu | Emergency
    visit_date = Column(DateTime)                       # scheduled date/time
    actual_visit_date = Column(DateTime)                # when it actually happened
    status = Column(String, default="Scheduled")        # Scheduled | Completed | Missed | Cancelled
    reason = Column(Text)
    # Outcome
    visit_notes = Column(Text)
    tests_done = Column(JSON, default=[])
    vitals = Column(JSON, default={})
    next_visit_date = Column(DateTime)
    # CHW diet validation at visit
    diet_validated_at_visit = Column(Boolean, default=False)
    diet_validation_note = Column(Text)
    # Doctor acceptance of CHW visit request
    doctor_accepted = Column(Boolean, default=False)
    chw_notified_acceptance = Column(Boolean, default=False)
    duration_minutes = Column(Integer, default=30)
    # Whose calendar this visit occupies. A doctor's own clinic visits sit on
    # the doctor's calendar; a CHW's patient visits (home visits, follow-ups)
    # sit on that specific CHW's own calendar — never shared with other CHWs
    # or written onto the doctor's schedule.
    provider_role = Column(String, default="doctor")   # "doctor" | "chw"
    provider_id = Column(Integer, nullable=True)        # doctors.id or chws.id, matching provider_role
    # Teleconsultation join info. The doctor/CHW only ever types the Google Meet
    # code (e.g. "abc-defg-hij") — the full join link is derived from it, and
    # that's what the patient sees.
    meeting_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="clinic_visits")

    @property
    def meeting_link(self):
        return f"https://meet.google.com/{self.meeting_id}" if self.meeting_id else None


class DoctorSettings(Base):
    """A doctor's working schedule: hours, lunch window, slot size, working days."""
    __tablename__ = "doctor_settings"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), unique=True)
    working_start = Column(String, default="09:00")
    working_end = Column(String, default="17:00")
    lunch_start = Column(String, default="12:00")
    lunch_end = Column(String, default="14:00")
    slot_minutes = Column(Integer, default=30)
    working_days = Column(JSON, default=[0, 1, 2, 3, 4, 5])  # Mon=0 ... Sun=6
    created_at = Column(DateTime, default=datetime.utcnow)


class DoctorBreak(Base):
    """One-off blocked time ranges on a specific date (conference, ward round, etc)."""
    __tablename__ = "doctor_breaks"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    date = Column(String)        # "YYYY-MM-DD"
    start_time = Column(String)  # "HH:MM"
    end_time = Column(String)    # "HH:MM"
    reason = Column(String, default="Blocked")
    created_at = Column(DateTime, default=datetime.utcnow)


class ChwSettings(Base):
    """A CHW's own working schedule — independent of the doctor's and of every
    other CHW's. Each CHW under a doctor has their own row here, keyed by
    chw_id, so their patient-visit calendars are never shared or merged."""
    __tablename__ = "chw_settings"

    id = Column(Integer, primary_key=True, index=True)
    chw_id = Column(Integer, ForeignKey("chws.id"), unique=True)
    working_start = Column(String, default="09:00")
    working_end = Column(String, default="17:00")
    lunch_start = Column(String, default="12:00")
    lunch_end = Column(String, default="14:00")
    slot_minutes = Column(Integer, default=30)
    working_days = Column(JSON, default=[0, 1, 2, 3, 4, 5])  # Mon=0 ... Sun=6
    created_at = Column(DateTime, default=datetime.utcnow)


class ChwBreak(Base):
    """One-off blocked time ranges on a specific date, on a specific CHW's own calendar."""
    __tablename__ = "chw_breaks"

    id = Column(Integer, primary_key=True, index=True)
    chw_id = Column(Integer, ForeignKey("chws.id"))
    date = Column(String)
    start_time = Column(String)
    end_time = Column(String)
    reason = Column(String, default="Blocked")
    created_at = Column(DateTime, default=datetime.utcnow)


class DietPlan(Base):
    """Diabetes diet plans — set by Doctor, optionally validated by CHW at visit."""
    __tablename__ = "diet_plans"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    created_by = Column(String)             # Doctor | CHW
    created_by_name = Column(String)
    plan_name = Column(String)
    # Meal structure
    morning = Column(Text)
    midmorning = Column(Text)
    lunch = Column(Text)
    evening = Column(Text)
    dinner = Column(Text)
    avoid_foods = Column(JSON, default=[])
    recommended_foods = Column(JSON, default=[])
    water_intake = Column(String)
    exercise = Column(Text)
    special_notes = Column(Text)
    active = Column(Boolean, default=True)
    # Simple nutrition targets — editable by Doctor and CHW
    calories_needed = Column(Float)
    protein_needed = Column(Float)
    # ── Clinical grounding (from MetaLife T2DM Nutrition Therapy Guide) ────
    # BMI group 1-4 (Asian-Indian cutoffs) this plan is based on.
    bmi_group = Column(Integer, nullable=True)
    bmi_value = Column(Float, nullable=True)
    macros = Column(JSON, default={})            # {carbs, protein, fat, fibre} as display strings
    meal_times = Column(JSON, default=[])         # [{time, label, en, hi, kcal}, ...] full-day bilingual plan
    strict_avoidance = Column(JSON, default=[])   # [{en, hi}, ...] never-eat list
    special_advice = Column(JSON, default=[])     # [{en, hi}, ...] clinical tips for this group
    # CHW validation
    chw_validated = Column(Boolean, default=False)
    chw_validated_note = Column(Text)
    chw_validated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="diet_plans")


class LabTest(Base):
    """Scheduled and completed lab tests."""
    __tablename__ = "lab_tests"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    ordered_by = Column(String)             # Doctor | CHW
    ordered_by_name = Column(String)
    test_name = Column(String, nullable=False)
    test_type = Column(String)              # Blood | Urine | Eye | Foot | HbA1c | Lipid | etc
    scheduled_date = Column(DateTime)
    completed_date = Column(DateTime)
    status = Column(String, default="Ordered")  # Ordered | Completed | Missed
    result_value = Column(String)
    result_notes = Column(Text)
    is_abnormal = Column(Boolean, default=False)
    clinic_visit_id = Column(Integer, ForeignKey("clinic_visits.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="lab_tests")


class PatientDocument(Base):
    """Uploaded/scanned reports, old test results, forms — added any time (not
    tied to a visit or a scheduled test). Visible to the patient, their CHW,
    doctor, and dietician, and downloadable by all of them."""
    __tablename__ = "patient_documents"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    title = Column(String, nullable=False)          # e.g. "HbA1c report - June 2023"
    doc_type = Column(String, default="Other")       # Lab Report | Prescription | Scan | Discharge Summary | Other
    notes = Column(Text)

    file_name = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    file_size = Column(Integer)                      # bytes
    file_data = Column(Text, nullable=False)          # base64-encoded file content

    uploaded_by = Column(String, nullable=False)      # CHW | Doctor | Dietician | Patient
    uploaded_by_id = Column(Integer)
    uploaded_by_name = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="documents")


class FoodLog(Base):
    """Simple patient-entered food diary — what they ate, calories, protein."""
    __tablename__ = "food_logs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    food_name = Column(String, nullable=False)
    calories = Column(Float)
    protein = Column(Float)
    logged_by = Column(String, default="Patient")
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="food_logs")


class ExerciseLog(Base):
    """Simple patient daily check-in for whether they did their recommended
    exercise — visible to CHW, Doctor, and Dietician for adherence tracking."""
    __tablename__ = "exercise_logs"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    completed = Column(Boolean, default=True)
    notes = Column(Text)
    logged_by = Column(String, default="Patient")
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient", back_populates="exercise_logs")

from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# Auth

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: int
    name: str


class LoginRequest(BaseModel):
    phone: str
    password: str
    role: str   # patient | chw | dietician | doctor


# Doctor

class DoctorCreate(BaseModel):
    name: str
    specialization: Optional[str] = None
    hospital: Optional[str] = None
    phone: str
    password: str


class DoctorOut(BaseModel):
    id: int
    name: str
    specialization: Optional[str]
    hospital: Optional[str]
    phone: str
    created_at: datetime

    model_config = {"from_attributes": True}


# CHW

class CHWCreate(BaseModel):
    name: str
    area: Optional[str] = None
    phone: str
    doctor_id: int
    password: str


class CHWOut(BaseModel):
    id: int
    name: str
    area: Optional[str]
    phone: str
    doctor_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


# Dietician
# A restricted, CHW-like role. Can only manage a patient's diet plans,
# food logs, and exercise plan — nothing else on the patient record.

class DieticianCreate(BaseModel):
    name: str
    specialization: Optional[str] = None
    phone: str
    doctor_id: int
    password: str


class DieticianOut(BaseModel):
    id: int
    name: str
    specialization: Optional[str]
    phone: str
    doctor_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientDieticianAssign(BaseModel):
    dietician_id: int


# Patient

class PatientCreate(BaseModel):
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    phone: str
    village: Optional[str] = None
    condition: Optional[str] = "Type 2 Diabetes"
    hba1c: Optional[float] = None
    weight: Optional[float] = None
    height_cm: Optional[float] = None
    chw_id: int
    doctor_id: int
    dietician_id: Optional[int] = None
    password: str
    # Extended Add Patient form fields
    title: Optional[str] = None
    dob: Optional[datetime] = None
    existing_id: Optional[str] = None
    blood_group: Optional[str] = None
    preferred_language: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    area_pin: Optional[str] = None
    referred_by_name: Optional[str] = None
    referred_by_specialization: Optional[str] = None
    channel: Optional[str] = None
    care_of: Optional[str] = None
    occupation: Optional[str] = None
    phone2: Optional[str] = None
    tag: Optional[str] = None

    @field_validator("height_cm")
    @classmethod
    def height_must_be_realistic(cls, v):
        if v is not None and v > 200:
            raise ValueError("Height looks too high — please check and re-enter (must be 200 cm or less).")
        return v

    @field_validator("phone")
    @classmethod
    def phone_must_be_valid(cls, v):
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) != 10 and not (len(digits) == 12 and digits.startswith("91")):
            raise ValueError("Phone number must contain exactly 10 digits.")
        return v


class PatientOut(BaseModel):
    id: int
    name: str
    age: Optional[int]
    gender: Optional[str]
    phone: str
    village: Optional[str]
    condition: Optional[str]
    hba1c: Optional[float]
    weight: Optional[float]
    height_cm: Optional[float] = None
    chw_id: int
    doctor_id: int
    dietician_id: Optional[int] = None
    created_at: datetime
    consent_given: Optional[bool] = False
    consent_given_at: Optional[datetime] = None
    consent_version: Optional[str] = None
    title: Optional[str] = None
    dob: Optional[datetime] = None
    existing_id: Optional[str] = None
    blood_group: Optional[str] = None
    preferred_language: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    area_pin: Optional[str] = None
    referred_by_name: Optional[str] = None
    referred_by_specialization: Optional[str] = None
    channel: Optional[str] = None
    care_of: Optional[str] = None
    occupation: Optional[str] = None
    phone2: Optional[str] = None
    tag: Optional[str] = None
    exercise_plan: Optional[str] = None
    exercise_updated_by: Optional[str] = None
    exercise_updated_by_name: Optional[str] = None
    exercise_updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExerciseUpdate(BaseModel):
    exercise_plan: str


class PatientOverviewOut(BaseModel):
    """Slim, diet-relevant view of a patient — used for the Dietician role so
    they get enough context (age, weight, condition, current exercise plan)
    without seeing the full chart (address, email, referral info, etc.)."""
    id: int
    name: str
    age: Optional[int]
    gender: Optional[str]
    condition: Optional[str]
    hba1c: Optional[float]
    weight: Optional[float]
    height_cm: Optional[float] = None
    village: Optional[str]
    exercise_plan: Optional[str] = None
    exercise_updated_by: Optional[str] = None
    exercise_updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# Consent / Terms & Conditions
# The patient reads MetaCare's Terms & Conditions and confirms agreement.
# `agree` must be true for the consent to be recorded.

class ConsentAccept(BaseModel):
    agree: bool
    version: Optional[str] = "1.0"


#  Daily Log

class LogCreate(BaseModel):
    blood_sugar: Optional[float] = None
    medication_taken: bool = True
    weight: Optional[float] = None
    raw_text: Optional[str] = None


class LogOut(BaseModel):
    id: int
    patient_id: int
    blood_sugar: Optional[float]
    medication_taken: Optional[bool]
    weight: Optional[float]
    raw_text: Optional[str]
    logged_by: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# Prescription

class PrescriptionCreate(BaseModel):
    patient_id: int
    medication_name: str
    dosage: str
    instructions: Optional[str] = None
    suggested_by: Optional[str] = "Doctor"


class PrescriptionOut(BaseModel):
    id: int
    patient_id: int
    medication_name: str
    dosage: Optional[str]
    instructions: Optional[str]
    suggested_by: Optional[str]
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


#  CHW Task

class TaskValidate(BaseModel):
    chw_note: str


class TaskOut(BaseModel):
    id: int
    patient_id: int
    chw_id: Optional[int]
    task_type: Optional[str]
    status: Optional[str]
    raw_patient_text: Optional[str]
    ai_summary: Optional[str]
    ai_classification: Optional[str]
    extracted_symptoms: Optional[List[str]]
    chw_validated: bool
    chw_validated_note: Optional[str]
    diet_plan_validated: Optional[bool]
    diet_plan_chw_note: Optional[str]
    critical_sugar_alert: Optional[bool] = False
    created_at: datetime

    model_config = {"from_attributes": True}


# Doctor Alert

class AlertOut(BaseModel):
    id: int
    patient_id: int
    doctor_id: Optional[int]
    alert_reason: Optional[str]
    doctor_context: Optional[str]
    source: Optional[str]
    is_resolved: bool
    visit_request_status: Optional[str]
    visit_requested_by: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# Notification

class NotificationCreate(BaseModel):
    patient_id: int
    message: str
    sent_by: str        # CHW | Doctor | System
    sent_by_name: str
    notif_type: Optional[str] = "message"


class NotificationOut(BaseModel):
    id: int
    patient_id: int
    sent_by: Optional[str]
    sent_by_name: Optional[str]
    message: Optional[str]
    notif_type: Optional[str]
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# AI endpoints

class DeepAnalysisRequest(BaseModel):
    question: str
    alert_id: int


# Clinic Visit

class VisitCreate(BaseModel):
    patient_id: int
    visit_type: str = "Mandatory"       # Mandatory | Impromptu | Emergency | Physical Visit | Teleconsultation
    visit_date: datetime
    reason: Optional[str] = None
    next_visit_date: Optional[datetime] = None
    duration_minutes: int = 30
    meeting_id: Optional[str] = None    # Google Meet code — Teleconsultation visits only


class VisitUpdate(BaseModel):
    status: Optional[str] = None        # Scheduled | Completed | Missed | Cancelled
    visit_notes: Optional[str] = None
    tests_done: Optional[List[str]] = None
    vitals: Optional[Dict[str, Any]] = None
    actual_visit_date: Optional[datetime] = None
    next_visit_date: Optional[datetime] = None
    diet_validated_at_visit: Optional[bool] = None
    diet_validation_note: Optional[str] = None
    meeting_id: Optional[str] = None    # Google Meet code — Teleconsultation visits only


class VisitOut(BaseModel):
    id: int
    patient_id: int
    scheduled_by: Optional[str]
    scheduled_by_name: Optional[str]
    visit_type: Optional[str]
    visit_date: Optional[datetime]
    actual_visit_date: Optional[datetime]
    status: Optional[str]
    reason: Optional[str]
    visit_notes: Optional[str]
    tests_done: Optional[List[str]]
    vitals: Optional[Dict[str, Any]]
    next_visit_date: Optional[datetime]
    diet_validated_at_visit: Optional[bool]
    diet_validation_note: Optional[str]
    doctor_accepted: Optional[bool]
    chw_notified_acceptance: Optional[bool]
    duration_minutes: Optional[int] = 30
    meeting_id: Optional[str] = None
    meeting_link: Optional[str] = None   # derived from meeting_id — what the patient uses to join
    created_at: datetime

    model_config = {"from_attributes": True}


class VisitEscalateRequest(BaseModel):
    reason: str
    visit_type: str = "Impromptu"       # Impromptu | Emergency
    preferred_date: Optional[datetime] = None   # CHW's proposed slot — checked against the doctor's calendar
    duration_minutes: int = 30


class VisitAcceptRequest(BaseModel):
    visit_date: datetime
    notes: Optional[str] = None
    duration_minutes: int = 30
    meeting_id: Optional[str] = None    # Google Meet code — Teleconsultation visits only


class FollowUpCreate(BaseModel):
    """Quick 'Schedule Follow-up' action off an existing/just-completed visit."""
    offset_days: int = 7                # 7 | 15 | 30 etc, or any custom number
    visit_type: str = "Physical Visit"  # Physical Visit | Teleconsultation
    visit_time: Optional[str] = None    # "HH:MM" — defaults to same time as the source visit
    reason: Optional[str] = None
    duration_minutes: int = 30
    meeting_id: Optional[str] = None    # Google Meet code — Teleconsultation visits only


# ── Doctor Calendar: working hours, breaks, slot grid ──────────────────────

class DoctorSettingsOut(BaseModel):
    doctor_id: int
    working_start: str
    working_end: str
    lunch_start: str
    lunch_end: str
    slot_minutes: int
    working_days: List[int]

    model_config = {"from_attributes": True}


class DoctorSettingsUpdate(BaseModel):
    working_start: Optional[str] = None
    working_end: Optional[str] = None
    lunch_start: Optional[str] = None
    lunch_end: Optional[str] = None
    slot_minutes: Optional[int] = None
    working_days: Optional[List[int]] = None


class DoctorBreakCreate(BaseModel):
    date: str            # "YYYY-MM-DD"
    start_time: str      # "HH:MM"
    end_time: str        # "HH:MM"
    reason: str = "Blocked"


class DoctorBreakOut(BaseModel):
    id: int
    doctor_id: int
    date: str
    start_time: str
    end_time: str
    reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class CalendarSlot(BaseModel):
    time: str                          # "HH:MM"
    status: str                        # available | booked | lunch | blocked | closed
    label: Optional[str] = None
    visit_id: Optional[int] = None
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    visit_type: Optional[str] = None
    break_id: Optional[int] = None
    reason: Optional[str] = None


class CalendarDayOut(BaseModel):
    date: str
    slot_minutes: int
    slots: List[CalendarSlot]


#  Diet Plan

class DietPlanCreate(BaseModel):
    patient_id: int
    plan_name: Optional[str] = "Diabetes Management Diet"
    morning: Optional[str] = None
    midmorning: Optional[str] = None
    lunch: Optional[str] = None
    evening: Optional[str] = None
    dinner: Optional[str] = None
    avoid_foods: Optional[List[str]] = []
    recommended_foods: Optional[List[str]] = []
    water_intake: Optional[str] = "8-10 glasses daily"
    exercise: Optional[str] = None
    special_notes: Optional[str] = None
    calories_needed: Optional[float] = None
    protein_needed: Optional[float] = None
    # Clinical grounding (MetaLife T2DM Nutrition Therapy Guide — bilingual)
    bmi_group: Optional[int] = None
    bmi_value: Optional[float] = None
    macros: Optional[Dict[str, Any]] = None
    meal_times: Optional[List[Dict[str, Any]]] = None
    strict_avoidance: Optional[List[Dict[str, Any]]] = None
    special_advice: Optional[List[Dict[str, Any]]] = None


class DietPlanUpdate(BaseModel):
    """Partial update to an existing diet plan — e.g. CHW or Doctor setting nutrition targets only."""
    plan_name: Optional[str] = None
    morning: Optional[str] = None
    midmorning: Optional[str] = None
    lunch: Optional[str] = None
    evening: Optional[str] = None
    dinner: Optional[str] = None
    avoid_foods: Optional[List[str]] = None
    recommended_foods: Optional[List[str]] = None
    water_intake: Optional[str] = None
    exercise: Optional[str] = None
    special_notes: Optional[str] = None
    calories_needed: Optional[float] = None
    protein_needed: Optional[float] = None
    bmi_group: Optional[int] = None
    bmi_value: Optional[float] = None
    macros: Optional[Dict[str, Any]] = None
    meal_times: Optional[List[Dict[str, Any]]] = None
    strict_avoidance: Optional[List[Dict[str, Any]]] = None
    special_advice: Optional[List[Dict[str, Any]]] = None


class DietPlanGenerateRequest(BaseModel):
    """Request to auto-generate a clinically-grounded bilingual diet plan.
    If bmi_group_override is omitted, the BMI group is computed from the
    patient's current weight and height (Asian-Indian cutoffs)."""
    bmi_group_override: Optional[int] = None
    additional_notes: Optional[str] = None


class DietValidateRequest(BaseModel):
    chw_note: str


class DietPlanOut(BaseModel):
    id: int
    patient_id: int
    created_by: Optional[str]
    created_by_name: Optional[str]
    plan_name: Optional[str]
    morning: Optional[str]
    midmorning: Optional[str]
    lunch: Optional[str]
    evening: Optional[str]
    dinner: Optional[str]
    avoid_foods: Optional[List[str]]
    recommended_foods: Optional[List[str]]
    water_intake: Optional[str]
    exercise: Optional[str]
    special_notes: Optional[str]
    active: bool
    calories_needed: Optional[float] = None
    protein_needed: Optional[float] = None
    bmi_group: Optional[int] = None
    bmi_value: Optional[float] = None
    macros: Optional[Dict[str, Any]] = None
    meal_times: Optional[List[Dict[str, Any]]] = None
    strict_avoidance: Optional[List[Dict[str, Any]]] = None
    special_advice: Optional[List[Dict[str, Any]]] = None
    chw_validated: Optional[bool]
    chw_validated_note: Optional[str]
    chw_validated_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


#  Lab Test

class LabTestCreate(BaseModel):
    patient_id: int
    test_name: str
    test_type: Optional[str] = "Blood"
    scheduled_date: datetime
    clinic_visit_id: Optional[int] = None


class LabTestUpdate(BaseModel):
    status: Optional[str] = None        # Ordered | Completed | Missed
    result_value: Optional[str] = None
    result_notes: Optional[str] = None
    is_abnormal: Optional[bool] = None
    completed_date: Optional[datetime] = None


class LabTestOut(BaseModel):
    id: int
    patient_id: int
    ordered_by: Optional[str]
    ordered_by_name: Optional[str]
    test_name: str
    test_type: Optional[str]
    scheduled_date: Optional[datetime]
    completed_date: Optional[datetime]
    status: Optional[str]
    result_value: Optional[str]
    result_notes: Optional[str]
    is_abnormal: Optional[bool]
    clinic_visit_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


# Food Log (simple calorie/protein diary)

class FoodLogCreate(BaseModel):
    food_name: str
    calories: Optional[float] = None
    protein: Optional[float] = None


class FoodLogOut(BaseModel):
    id: int
    patient_id: int
    food_name: str
    calories: Optional[float]
    protein: Optional[float]
    logged_by: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# Exercise Log (patient daily check-in: did they do the recommended exercise)

class ExerciseLogCreate(BaseModel):
    completed: bool = True
    notes: Optional[str] = None


class ExerciseLogOut(BaseModel):
    id: int
    patient_id: int
    completed: bool
    notes: Optional[str]
    logged_by: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

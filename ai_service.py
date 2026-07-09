"""
ai_service.py – all Gemini API calls for MetaCare clinical reasoning.
Updated for v2: Visit Escalation, Diet Plans, and Chatbot.
"""

import os
import json
import httpx
from typing import Optional
from dotenv import load_dotenv
import diet_reference

# Load environment variables
load_dotenv()

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = "gemini-1.5-flash"   # Standardized to the reliable 1.5-flash model
API_KEY = os.getenv("GEMINI_API_KEY", "")


def _call(prompt: str, system: str = "", max_tokens: int = 1024) -> dict:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")

    full_prompt = f"{system}\n\n{prompt}" if system else prompt

    url = f"{GEMINI_API_URL}/{MODEL}:generateContent?key={API_KEY}"
    body = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens}
    }

    response = httpx.post(url, json=body, timeout=60)
    response.raise_for_status()
    data = response.json()

    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]

    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```", 2)[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip().rstrip("`").strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {"raw_response": raw_text}


# Patient report analysis

def analyze_patient_report(
    patient_name: str,
    patient_age: int,
    condition: str,
    report_text: str,
    blood_sugar: Optional[float],
    medication_taken: bool,
    recent_logs: list,
) -> dict:
    prompt = f"""You are a clinical AI for a rural India diabetes management system. Analyze the patient report below.

Patient: {patient_name}, {patient_age}y, {condition}
Report (may be Hinglish): "{report_text}"
Blood sugar: {blood_sugar or 'not provided'} mg/dL
Medication taken today: {medication_taken}
Recent logs (last 5 days): {json.dumps(recent_logs, default=str)}

Respond ONLY with a valid JSON object using these exact keys:
{{
  "chw_summary": "2-3 sentence plain-language summary for the CHW",
  "doctor_context": "clinical summary for the doctor with trend analysis",
  "extracted_symptoms": ["symptom1", "symptom2"],
  "classification": "Routine|Needs Follow Up|Emergency",
  "suggested_action": "what CHW should do next",
  "severity_note": "brief severity justification",
  "translated_text": "English translation of the patient's Hinglish text",
  "auto_notify_chw": true,
  "auto_notify_patient": false,
  "auto_notification_message": "If auto_notify_patient is true, message to send to patient in Hinglish"
}}"""

    fallback = {
        "chw_summary": "Manual review needed. AI unavailable.",
        "doctor_context": "Patient submitted a report. AI analysis unavailable.",
        "extracted_symptoms": [],
        "classification": "Needs Follow Up",
        "suggested_action": "Call patient and review manually.",
        "severity_note": "AI service unavailable.",
        "translated_text": report_text,
        "auto_notify_chw": True,
        "auto_notify_patient": False,
        "auto_notification_message": "",
    }
    try:
        result = _call(prompt)
        return {**fallback, **result}
    except Exception as e:
        fallback["error"] = str(e)
        return fallback


# CHW task validation

def validate_chw_task(
    patient_name: str,
    patient_age: int,
    original_report: str,
    initial_ai_summary: str,
    chw_note: str,
    recent_logs: list,
) -> dict:
    prompt = f"""A Community Health Worker (CHW) has just validated a patient task after calling the patient.

Patient: {patient_name}, {patient_age}y
Original patient report: "{original_report}"
AI initial summary: "{initial_ai_summary}"
CHW validation note after calling patient: "{chw_note}"
Recent history: {json.dumps(recent_logs, default=str)}

Based on the CHW's direct contact, provide an updated assessment.
Respond ONLY with valid JSON:
{{
  "chw_summary": "updated CHW-facing summary",
  "doctor_context": "updated clinical context for doctor with CHW findings",
  "classification": "Routine|Needs Follow Up|Emergency",
  "suggested_action": "recommended next step",
  "severity_note": "why this classification was chosen",
  "should_escalate_visit": false,
  "visit_type": "Impromptu|Emergency|Mandatory",
  "visit_reason": "why a visit is needed if should_escalate_visit is true",
  "auto_notify_patient": false,
  "patient_notification_message": "message to send to patient in Hinglish if auto_notify_patient is true"
}}"""

    fallback = {
        "chw_summary": chw_note,
        "doctor_context": f"CHW validation note: {chw_note}",
        "classification": "Needs Follow Up",
        "suggested_action": "Doctor to review.",
        "severity_note": "AI unavailable; CHW note used as-is.",
        "should_escalate_visit": False,
        "visit_type": "Impromptu",
        "visit_reason": "",
        "auto_notify_patient": False,
        "patient_notification_message": "",
    }
    try:
        result = _call(prompt)
        return {**fallback, **result}
    except Exception as e:
        fallback["error"] = str(e)
        return fallback


#  Auto-trend alert generation

def generate_trend_alert(
    patient_name: str,
    patient_age: int,
    gender: str,
    condition: str,
    logs: list,
    prescription: Optional[dict] = None,
) -> dict:
    sugars = [l["blood_sugar"] for l in logs if l.get("blood_sugar")]
    missed_meds = sum(1 for l in logs if not l.get("medication_taken", True))

    prompt = f"""You are a clinical AI monitoring a rural India diabetes patient's weekly trend.

Patient: {patient_name}, {patient_age}y {gender}, {condition}
Blood sugar readings (oldest→newest): {sugars}
Missed medication doses this week: {missed_meds}
Current prescription: {json.dumps(prescription, default=str) if prescription else 'None'}
Recent log notes: {json.dumps([l.get('raw_text', '') for l in logs], default=str)}

Evaluate whether an alert should be sent to the doctor.
Respond ONLY with valid JSON:
{{
  "should_alert": true,
  "alert_reason": "one-line reason for the doctor",
  "doctor_context": "clinical summary: trend analysis, missed meds, symptoms, recommended action",
  "should_schedule_visit": false,
  "visit_type": "Mandatory",
  "visit_reason": "reason for scheduling a visit if should_schedule_visit is true",
  "auto_notify_patient": false,
  "patient_notification_message": "message to send to patient in Hinglish if auto_notify_patient is true"
}}"""

    fallback = {
        "should_alert": False,
        "alert_reason": "",
        "doctor_context": "",
        "should_schedule_visit": False,
        "visit_type": "Mandatory",
        "visit_reason": "",
        "auto_notify_patient": False,
        "patient_notification_message": "",
    }
    try:
        result = _call(prompt)
        return {**fallback, **result}
    except Exception as e:
        fallback["error"] = str(e)
        return fallback


# ─── Deep doctor analysis ─────────────────────────────────────────────────────

def deep_doctor_analysis(
    doctor_question: str,
    patient_name: str,
    patient_age: int,
    condition: str,
    alert_reason: str,
    recent_logs: list,
) -> dict:
    prompt = f"""You are a clinical consultant AI helping a doctor review a rural India diabetes patient.

Patient: {patient_name}, {patient_age}y, {condition}
Alert reason: {alert_reason}
Recent logs: {json.dumps(recent_logs, default=str)}
Doctor's question: "{doctor_question}"

Provide a concise 3-4 sentence clinical analysis addressing the doctor's question.
Respond ONLY with valid JSON: {{"analysis": "..."}}"""

    fallback = {"analysis": "AI analysis unavailable. Please consult clinical guidelines."}
    try:
        result = _call(prompt)
        return {**fallback, **result}
    except Exception as e:
        fallback["error"] = str(e)
        return fallback


# ─── Diet plan generation ─────────────────────────────────────────────────────

def _group_to_plan_fields(group: dict, bmi_value: Optional[float]) -> dict:
    """Convert a diet_reference BMI-group entry into DietPlan-shaped fields,
    including the legacy single-string meal fields (for older UI code) and
    the new bilingual/time-based fields."""
    meals_by_label = {m["label"]: m for m in group["meal_times"] if m["label"]}
    morning = meals_by_label.get("Breakfast")
    lunch = meals_by_label.get("Lunch")
    dinner = meals_by_label.get("Dinner")
    # Combine the two snack slots (mid-morning + evening) into the legacy fields.
    snack_entries = [m for m in group["meal_times"] if m["label"] == "Snack"]
    midmorning = snack_entries[0] if len(snack_entries) > 0 else None
    evening = snack_entries[1] if len(snack_entries) > 1 else None

    def bilingual(m):
        if not m:
            return None
        return f"{m['time']} — {m['en']} | {m['hi']}"

    return {
        "plan_name": f"T2DM Diet — Group {group['group_no']} ({group['name']['en']} / {group['name']['hi']})",
        "morning": bilingual(morning),
        "midmorning": bilingual(midmorning),
        "lunch": bilingual(lunch),
        "evening": bilingual(evening),
        "dinner": bilingual(dinner),
        "avoid_foods": group["avoid_foods"],
        "recommended_foods": group["recommended_foods"],
        "water_intake": group["water_intake"]["en"] + " | " + group["water_intake"]["hi"],
        "exercise": group["exercise"]["en"] + " | " + group["exercise"]["hi"],
        "special_notes": f"BMI range {group['bmi_range']} — {group['calorie_target']} kcal/day. "
                          f"{group['key_focus']['en']} / {group['key_focus']['hi']}",
        "bmi_group": group["group_no"],
        "bmi_value": bmi_value,
        "macros": group["macros"],
        "meal_times": group["meal_times"],
        "strict_avoidance": group["strict_avoidance"],
        "special_advice": group["special_advice"],
    }


def generate_diet_plan(
    patient_name: str,
    patient_age: int,
    gender: str,
    condition: str,
    hba1c: Optional[float],
    weight: Optional[float],
    height_cm: Optional[float] = None,
    recent_logs: Optional[list] = None,
    prescription: Optional[dict] = None,
    additional_notes: str = "",
    bmi_group_override: Optional[int] = None,
) -> dict:
    """Generate a clinically-grounded, bilingual (English + Hindi) T2DM diet
    plan based on the MetaLife T2DM Nutrition Therapy Guide (RSSDI 2017,
    ICMR-NIN 2024, ADA Guidelines, Asian Indian BMI cutoffs, DiRECT Trial).

    The BMI group (1-4) is computed from weight+height using Asian-Indian
    cutoffs unless bmi_group_override is given (e.g. a Dietician manually
    picking a group when height isn't on file). The reference plan for that
    group is always the deterministic fallback — the AI call is only used
    to add a short personalised "special_notes" paragraph on top of it.
    """
    recent_logs = recent_logs or []
    bmi_value = diet_reference.compute_bmi(weight, height_cm)
    if bmi_group_override:
        group_no = bmi_group_override
    elif bmi_value:
        group_no = diet_reference.get_bmi_group(bmi_value)
    else:
        group_no = 1
    group = diet_reference.BMI_GROUPS.get(group_no, diet_reference.BMI_GROUPS[1])

    fallback = _group_to_plan_fields(group, bmi_value)

    prompt = f"""You are a clinical dietitian AI. A patient has been placed in BMI Group {group['group_no']}
({group['name']['en']}, BMI range {group['bmi_range']}) of the MetaLife T2DM Nutrition Therapy Guide.
This guide's meal plan, macros, and avoidance lists are FIXED clinical content and must NOT be changed.

Patient: {patient_name}, {patient_age}y {gender}, {condition}
HbA1c: {hba1c or 'unknown'}%  Weight: {weight or 'unknown'} kg  Height: {height_cm or 'unknown'} cm  BMI: {bmi_value or 'unknown'}
Current prescription: {json.dumps(prescription, default=str) if prescription else 'None'}
Recent blood sugar trend: {[l.get('blood_sugar') for l in recent_logs[:7] if l.get('blood_sugar')]}
Doctor/CHW/Dietician notes: "{additional_notes}"

Write ONLY a short (2-3 sentence) bilingual (English then Hindi) "special_notes" addendum that
personalises the fixed Group {group['group_no']} plan to this patient's readings/history/notes above
(e.g. flag hypoglycemia risk if on insulin/sulfonylurea with low readings, or reinforce a habit they're missing).
Do NOT invent a new meal plan.
Respond ONLY with valid JSON: {{"special_notes": "English sentence(s). Hindi sentence(s)."}}"""

    try:
        result = _call(prompt, max_tokens=400)
        note = result.get("special_notes") if isinstance(result, dict) else None
        if note:
            fallback["special_notes"] = fallback["special_notes"] + " — " + note
    except Exception as e:
        fallback["error"] = str(e)
    return fallback


# ─── Chatbot response ─────────────────────────────────────────────────────────

def chatbot_response(
    user_message: str,
    user_role: str,
    patient_context: Optional[dict] = None,
) -> dict:
    context_str = ""
    if patient_context:
        context_str = f"\n\nPatient context available:\n{json.dumps(patient_context, default=str)}"

    system = f"""You are MetaCare Assistant, an AI chatbot embedded in the MetaCare rural diabetes management system in India.
You help {user_role}s with MetaCare platform usage and diabetes care basics.

STRICT RULES:
1. Only answer questions about: MetaCare platform usage, diabetes management, medication reminders, diet for diabetes, when to seek care, CHW workflow, doctor alerts, clinic visits, lab tests, and diet plans.
2. For anything unrelated, politely say: "Main sirf MetaCare aur diabetes care ke baare mein help kar sakta hun."
3. Keep answers SHORT and practical — 2-4 sentences maximum.
4. For patients: mix simple Hindi/English (Hinglish) when helpful.
5. EMERGENCIES (chest pain, sugar >400, unconscious, difficulty breathing): ALWAYS say "TURANT 108 call karein ya hospital jaayein!"
6. Never give specific drug dosage advice — say "apne doctor se poochhen".
7. If patient context is provided, use it to give personalised answers.{context_str}

Respond ONLY with valid JSON: {{"reply": "your answer here", "is_emergency": false}}"""

    fallback = {
        "reply": "Main abhi available nahi hun. Please apne CHW ya doctor se contact karein.",
        "is_emergency": False,
    }
    try:
        result = _call(user_message, system=system, max_tokens=300)
        if isinstance(result, dict) and "raw_response" in result:
            return {"reply": result["raw_response"], "is_emergency": False}
        return {**fallback, **result}
    except Exception as e:
        fallback["error"] = str(e)
        return fallback
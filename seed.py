"""
seed.py – Populate MetaCare database with realistic demo data (v2.0).

Creates:
  • 1 Doctor  — Dr. Anil Mandloi
  • 1 CHW     — Priya Singh
  • 2 Patients — Ramesh Kumar (worsening trend) & Sunita Devi (emergency)
  • 14 days of daily logs per patient
  • Prescriptions, CHW tasks, doctor alerts, notifications
  • NEW: Diet Plans, Lab Tests, and Clinic Visits (including escalations)
"""

from database import SessionLocal, engine, Base
import models
import diet_reference
from auth import hash_password
from datetime import datetime, timedelta
import json

# ─── Passwords (change before going live) ─────────────────────────────────────
DOCTOR_PASSWORD     = "doctor123"
CHW_PASSWORD        = "chw123"
DIETICIAN_PASSWORD  = "dietician123"
RAMESH_PASSWORD     = "ramesh123"
SUNITA_PASSWORD     = "sunita123"


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if db.query(models.Doctor).first():
        db.close()
        print("Database already seeded. Skipping.")
        return

    now = datetime.utcnow()

    # ── Doctor ─────────────────────────────────────────────────────────────────
    doctor = models.Doctor(
        name="Dr. Anil Mandloi",
        specialization="Diabetologist",
        hospital="Indore District Hospital",
        phone="+91-9801234567",
        hashed_password=hash_password(DOCTOR_PASSWORD),
    )
    db.add(doctor)
    db.flush()

    # ── CHW ────────────────────────────────────────────────────────────────────
    chw = models.CHW(
        name="Priya Singh",
        area="Dewas Block, Madhya Pradesh",
        phone="+91-9712345678",
        doctor_id=doctor.id,
        hashed_password=hash_password(CHW_PASSWORD),
    )
    db.add(chw)
    db.flush()

    # ── Dietician ──────────────────────────────────────────────────────────────
    # Restricted role: can only manage a patient's diet plans, food logs, and
    # exercise plan. A patient can be under a CHW AND a Dietician at once.
    dietician = models.Dietician(
        name="Meena Verma",
        specialization="Diabetic Nutrition",
        phone="+91-9723456789",
        doctor_id=doctor.id,
        hashed_password=hash_password(DIETICIAN_PASSWORD),
    )
    db.add(dietician)
    db.flush()

    # ══════════════════════════════════════════════════════════════════════════
    # PATIENT 1 — Ramesh Kumar (worsening, multiple missed meds)
    # ══════════════════════════════════════════════════════════════════════════
    ramesh = models.Patient(
        name="Ramesh Kumar",
        age=52,
        gender="Male",
        phone="+91-9876543210",
        village="Khategaon, Dewas",
        condition="Type 2 Diabetes",
        hba1c=8.2,
        weight=74.0,
        height_cm=168.0,   # BMI ≈ 26.2 → Group 3 (Obese I)
        chw_id=chw.id,
        doctor_id=doctor.id,
        dietician_id=dietician.id,
        hashed_password=hash_password(RAMESH_PASSWORD),
        consent_given=True,
        consent_given_at=now - timedelta(days=20),
        consent_version="1.0",
        title="Mr.",
        blood_group="B+",
        preferred_language="Hindi",
        city="Dewas",
        occupation="Farmer",
        exercise_plan="20 min brisk walk every morning before breakfast. Light stretching in the evening. Avoid strenuous work right after meals.",
        exercise_updated_by="DOCTOR",
        exercise_updated_by_name=doctor.name,
        exercise_updated_at=now - timedelta(days=20),
    )
    db.add(ramesh)
    db.flush()

    # Prescription for Ramesh
    rx_ramesh = models.Prescription(
        patient_id=ramesh.id,
        medication_name="Metformin 500mg",
        dosage="1 tablet twice daily after meals",
        instructions="Take with food. Avoid alcohol.",
        suggested_by="Doctor",
        active=True,
        created_at=now - timedelta(days=20),
    )
    db.add(rx_ramesh)

    # Diet Plan for Ramesh — grounded in the MetaLife T2DM Nutrition Therapy
    # Guide, BMI Group 3 (Obese Class I, BMI 25.0-27.4). Validated by CHW.
    g3 = diet_reference.BMI_GROUPS[3]
    meals_by_label = {m["label"]: m for m in g3["meal_times"] if m["label"]}
    snacks = [m for m in g3["meal_times"] if m["label"] == "Snack"]

    def _bl(m):
        return f"{m['time']} — {m['en']} | {m['hi']}" if m else None

    diet_ramesh = models.DietPlan(
        patient_id=ramesh.id,
        created_by="DOCTOR",
        created_by_name=doctor.name,
        plan_name=f"T2DM Diet — Group 3 ({g3['name']['en']} / {g3['name']['hi']})",
        morning=_bl(meals_by_label.get("Breakfast")),
        midmorning=_bl(snacks[0] if snacks else None),
        lunch=_bl(meals_by_label.get("Lunch")),
        evening=_bl(snacks[1] if len(snacks) > 1 else None),
        dinner=_bl(meals_by_label.get("Dinner")),
        avoid_foods=g3["avoid_foods"],
        recommended_foods=g3["recommended_foods"],
        water_intake=g3["water_intake"]["en"] + " | " + g3["water_intake"]["hi"],
        exercise=g3["exercise"]["en"] + " | " + g3["exercise"]["hi"],
        special_notes=f"BMI range {g3['bmi_range']} — {g3['calorie_target']} kcal/day. "
                       f"{g3['key_focus']['en']} / {g3['key_focus']['hi']}",
        bmi_group=3,
        bmi_value=diet_reference.compute_bmi(74.0, 168.0),
        macros=g3["macros"],
        meal_times=g3["meal_times"],
        strict_avoidance=g3["strict_avoidance"],
        special_advice=g3["special_advice"],
        active=True,
        calories_needed=1300,
        protein_needed=100,
        chw_validated=True,
        chw_validated_note="Ramesh ji samajh gaye hain, lekin shaadi mein meetha kha liya tha.",
        chw_validated_at=now - timedelta(days=5),
        created_at=now - timedelta(days=20),
    )
    db.add(diet_ramesh)

    # Completed Lab Test for Ramesh
    lab_ramesh = models.LabTest(
        patient_id=ramesh.id,
        ordered_by="DOCTOR",
        ordered_by_name=doctor.name,
        test_name="HbA1c",
        test_type="Blood",
        scheduled_date=now - timedelta(days=25),
        completed_date=now - timedelta(days=23),
        status="Completed",
        result_value="8.2%",
        is_abnormal=True,
        created_at=now - timedelta(days=25),
    )
    db.add(lab_ramesh)

    # Past Clinic Visit for Ramesh
    visit_ramesh = models.ClinicVisit(
        patient_id=ramesh.id,
        scheduled_by="DOCTOR",
        scheduled_by_name=doctor.name,
        visit_type="Mandatory",
        visit_date=now - timedelta(days=20),
        actual_visit_date=now - timedelta(days=20),
        status="Completed",
        reason="Initial diabetes consultation",
        visit_notes="Diagnosed with T2DM. Prescribed Metformin and diet plan.",
        tests_done=["HbA1c checked recently"],
        vitals={"BP": "130/85", "Weight": "74 kg"},
        doctor_accepted=True,
        created_at=now - timedelta(days=25),
    )
    db.add(visit_ramesh)

    # 14 days of logs — realistic worsening trend
    ramesh_logs = [
        (14, 118, True,  74.8, "Aaj bilkul theek hai. Subah naashta kiya aur dawai li."),
        (13, 124, True,  74.6, "Halki weakness thi subah mein, paani zyada piya."),
        (12, 131, True,  74.5, "Subah walk ki 20 min. Sugar theek lag raha hai."),
        (11, 129, True,  74.4, "Sab theek hai, dawai time pe li."),
        (10, 143, True,  74.2, "Thodi bhookh zyada lag rahi hai, kuch meetha khaya."),
        (9,  156, False, 74.0, "Dawai bhool gayi, bazar gaya tha poore din."),
        (8,  162, True,  73.9, "Aaj yaad se dawai li. Thoda chakkar sa."),
        (7,  171, False, 73.8, "Shaadi mein tha, dawai nahi li. Bahut meetha khaya."),
        (6,  193, True,  73.5, "Pet mein halka dard aur chakkar aa rahe hain dopahar se."),
        (5,  220, False, 73.2, "Dawai nahi li, market mein tha. Haath thoda kaanp raha."),
        (4,  238, False, 73.0, "Bohot kamzori. Dawai phir miss ho gayi. Bhookh nahi."),
        (3,  245, False, 72.8, "Bohot kamzori, haath kaanp rahe hain, neend nahi aayi raat."),
        (2,  258, True,  72.6, "Aaj dawai li. Phir bhi chakkar aa rahe hain."),
        (1,  261, True,  72.5, "Aankhein bhi dhundhli ho rahi hain. Bohot bura feel ho raha hai."),
    ]

    for days_ago, sugar, meds, weight, text in ramesh_logs:
        ts = now - timedelta(days=days_ago)
        db.add(models.DailyLog(
            patient_id=ramesh.id,
            blood_sugar=sugar,
            medication_taken=meds,
            weight=weight,
            raw_text=text,
            logged_by="Patient",
            created_at=ts,
        ))

    # Sample food log entries for Ramesh
    ramesh_food = [
        (0, "2 Daliya bowl with vegetables", 220, 7),
        (0, "1 Roti + Dal + Sabzi", 380, 14),
        (1, "Guava", 60, 1.5),
    ]
    for days_ago, food, cal, protein in ramesh_food:
        db.add(models.FoodLog(
            patient_id=ramesh.id, food_name=food, calories=cal, protein=protein,
            logged_by="Patient", created_at=now - timedelta(days=days_ago, hours=2),
        ))

    # CHW tasks for Ramesh
    db.add(models.CHWTask(
        patient_id=ramesh.id,
        chw_id=chw.id,
        task_type="Patient Report",
        status="Pending",
        raw_patient_text="Bohot kamzori, haath kaanp rahe hain, neend nahi aayi raat.",
        ai_summary=(
            "Patient Ramesh (52M) reports trembling hands, extreme weakness and insomnia. "
            "Sugar trending sharply upward: 118→245 mg/dL over 14 days. "
            "Missed medication 5 times. Call urgently."
        ),
        ai_classification="Needs Follow Up",
        extracted_symptoms=["trembling hands", "weakness", "insomnia"],
        created_at=now - timedelta(days=3),
    ))

    # Doctor alerts for Ramesh
    db.add(models.DoctorAlert(
        patient_id=ramesh.id,
        doctor_id=doctor.id,
        alert_reason="Worsening trend + blurred vision: 118→261 mg/dL over 14 days",
        doctor_context=(
            "Patient Ramesh Kumar shows consistent upward blood sugar trend "
            "with 5 missed medication doses. Recent report includes blurred vision."
        ),
        source="AutoTrend",
        created_at=now - timedelta(hours=6),
    ))

    # Notifications for Ramesh
    db.add(models.Notification(
        patient_id=ramesh.id,
        sent_by="CHW",
        sent_by_name="Priya Singh",
        message="Ramesh ji, aapka sugar zyada badh raha hai. Aaj shaam dawai zaroor lein.",
        notif_type="message",
        created_at=now - timedelta(days=1, hours=2),
    ))

    # ══════════════════════════════════════════════════════════════════════════
    # PATIENT 2 — Sunita Devi (chest pain emergency, Visit Escalation)
    # ══════════════════════════════════════════════════════════════════════════
    sunita = models.Patient(
        name="Sunita Devi",
        age=58,
        gender="Female",
        phone="+91-9876543211",
        village="Bagli, Dewas",
        condition="Type 2 Diabetes",
        hba1c=9.1,
        weight=68.0,
        height_cm=155.0,   # BMI ≈ 28.3 → Group 4 (Obese II+)
        chw_id=chw.id,
        doctor_id=doctor.id,
        hashed_password=hash_password(SUNITA_PASSWORD),
        consent_given=True,
        consent_given_at=now - timedelta(days=30),
        consent_version="1.0",
        title="Mrs.",
        blood_group="O+",
        preferred_language="Hindi",
        city="Bagli",
        occupation="Homemaker",
        exercise_plan="10-15 min gentle walk only, avoid exertion until chest pain is evaluated by doctor.",
        exercise_updated_by="DOCTOR",
        exercise_updated_by_name=doctor.name,
        exercise_updated_at=now - timedelta(days=30),
    )
    db.add(sunita)
    db.flush()

    rx_sunita = models.Prescription(
        patient_id=sunita.id,
        medication_name="Glipizide 5mg + Metformin 500mg",
        dosage="1 tablet of each, twice daily before meals",
        suggested_by="Doctor",
        active=True,
        created_at=now - timedelta(days=30),
    )
    db.add(rx_sunita)

    # Abnormal Lab Test for Sunita (Triggers Alert)
    lab_sunita = models.LabTest(
        patient_id=sunita.id,
        ordered_by="DOCTOR",
        ordered_by_name=doctor.name,
        test_name="Lipid Profile",
        test_type="Blood",
        scheduled_date=now - timedelta(days=4),
        completed_date=now - timedelta(days=2),
        status="Completed",
        result_value="LDL 185 mg/dL",
        result_notes="High cholesterol. Risk of cardiovascular event.",
        is_abnormal=True,
        created_at=now - timedelta(days=4),
    )
    db.add(lab_sunita)

    # Escalated Clinic Visit for Sunita (Requested by CHW, waiting for Doctor to accept)
    escalated_visit = models.ClinicVisit(
        patient_id=sunita.id,
        scheduled_by="CHW",
        scheduled_by_name=chw.name,
        visit_type="Emergency",
        visit_date=now + timedelta(days=1), # Provisional
        status="Scheduled",
        reason="Severe chest pain and shortness of breath.",
        doctor_accepted=False,
        created_at=now - timedelta(hours=2),
    )
    db.add(escalated_visit)
    db.flush()

    # Doctor Alert for the Visit Request
    db.add(models.DoctorAlert(
        patient_id=sunita.id,
        doctor_id=doctor.id,
        alert_reason="Visit Request (Emergency): Severe chest pain and shortness of breath.",
        doctor_context=(
            f"CHW {chw.name} is requesting an Emergency clinic visit for Sunita Devi. "
            f"Patient is reporting acute chest pain. Recent Lipid Profile showed LDL 185 mg/dL."
        ),
        source="VisitRequest",
        visit_request_status="Requested",
        visit_requested_by=chw.name,
        created_at=now - timedelta(hours=2),
    ))

    sunita_logs = [
        (14, 198, True,  68.5, "Sugar zyada hai lekin dawai le rahi hoon."),
        (13, 204, True,  68.4, "Thaki hui hoon. Pair mein sujan hai."),
        (12, 191, True,  68.3, "Pair ki sujan thodi kam hui. Dawai li."),
        (11, 210, True,  68.2, "Chakkar aate hain. Bhookh nahi."),
        (10, 218, False, 68.0, "Mela tha gaon mein, dawai nahi li."),
        (9,  225, True,  67.8, "Ulti jaisi feel ho rahi hai subah se."),
        (8,  232, True,  67.7, "Sar dard aur kamzori. Dawai li."),
        (7,  219, True,  67.6, "Thoda better. Par pair dard ho raha hai."),
        (6,  228, True,  67.5, "Neend nahi aayi. Sar bhaari hai."),
        (5,  241, False, 67.3, "Gaon se bahar thi, dawai nahi li."),
        (4,  255, True,  67.2, "Aaj dawai li. Aankhein dhundhli ho rahi hain."),
        (3,  268, True,  67.0, "Bahut kamzori. Seene mein halka dard."),
        (2,  274, True,  66.8, "Seene mein dard badh gaya. Bahut ghabra rahi hoon."),
        (1,  280, True,  66.5, "Seene mein bahut dard ho raha hai, bahut takleef hai."),
    ]

    for days_ago, sugar, meds, weight, text in sunita_logs:
        ts = now - timedelta(days=days_ago)
        db.add(models.DailyLog(
            patient_id=sunita.id,
            blood_sugar=sugar,
            medication_taken=meds,
            weight=weight,
            raw_text=text,
            logged_by="Patient",
            created_at=ts,
        ))

    db.add(models.CHWTask(
        patient_id=sunita.id,
        chw_id=chw.id,
        task_type="Emergency",
        status="Pending",
        raw_patient_text="Seene mein bahut dard ho raha hai, bahut takleef hai.",
        ai_summary=(
            "EMERGENCY: Sunita Devi (58F) reports severe chest pain. "
            "Blood sugar 280 mg/dL. Requires immediate hospital transport."
        ),
        ai_classification="Emergency",
        extracted_symptoms=["severe chest pain", "distress"],
        critical_sugar_alert=True,
        created_at=now - timedelta(days=1),
    ))

    db.add(models.DoctorAlert(
        patient_id=sunita.id,
        doctor_id=doctor.id,
        alert_reason="Abnormal test result: Lipid Profile = LDL 185 mg/dL",
        doctor_context="Lab test Lipid Profile returned abnormal result. High cardiovascular risk.",
        source="System",
        created_at=now - timedelta(days=2),
    ))

    db.add(models.Notification(
        patient_id=sunita.id,
        sent_by="CHW",
        sent_by_name="Priya Singh",
        message="Aapke liye ek Emergency clinic visit request ki gayi hai. Doctor ke confirm karne par bataya jaayega.",
        notif_type="visit",
        created_at=now - timedelta(hours=2),
    ))

    db.commit()
    db.close()

    print("[SUCCESS] Seed complete (v2.0 with Visits, Diets, and Tests)!")
    print()
    print("=" * 55)
    print("  DEMO CREDENTIALS")
    print("=" * 55)
    print(f"  Doctor  : phone=+91-9801234567  password={DOCTOR_PASSWORD}")
    print(f"  CHW       : phone=+91-9712345678  password={CHW_PASSWORD}")
    print(f"  Dietician : phone=+91-9723456789  password={DIETICIAN_PASSWORD}")
    print(f"  Patient1: phone=+91-9876543210  password={RAMESH_PASSWORD}")
    print(f"  Patient2: phone=+91-9876543211  password={SUNITA_PASSWORD}")
    print("=" * 55)
    print()


if __name__ == "__main__":
    seed()
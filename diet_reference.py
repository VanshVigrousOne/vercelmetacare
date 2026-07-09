"""
diet_reference.py — Structured, bilingual (English + Hindi) clinical diet
reference data, extracted from the "MetaLife Metabolic Clinic — T2DM
Nutrition Therapy Guide" (RSSDI 2017 · ICMR-NIN 2024 · ADA Guidelines ·
Asian Indian BMI Cutoffs · DiRECT Trial).

This is the single source of truth for diet-plan content across the app:
 - ai_service.generate_diet_plan() grounds/validates the AI output against it
   and uses it as a deterministic fallback when the AI is unavailable.
 - main.py exposes it directly via /diet-reference endpoints so the Doctor,
   CHW, and Dietician UIs can show the full clinical guide (meal times,
   substitution tables, GI chart) â€” not just a free-text plan.

BMI cutoffs use ASIAN INDIAN thresholds (lower than WHO/Western), per the
RSSDI/IDF consensus that metabolic risk in Indians begins at BMI 23, not 25.
"""

CLINICAL_NOTES = {
    "waist_circumference": {
        "en": "Men < 90 cm, Women < 80 cm",
        "hi": "पुरुष < 90 सेमी, महिलाएं < 80 सेमी",
    },
    "calorie_formula": {
        "en": "Body weight (kg) x 20-22 = maintenance kcal. Subtract 500 for weight loss.",
        "hi": "शरीर का वज़न (kg) x 20-22 = आवश्यक कैलोरी। वज़न घटाने के लिए 500 घटाएं।",
    },
    "asian_bmi_note": {
        "en": "Asian Indians have higher body fat at the same BMI vs Western populations (RSSDI/IDF consensus). Metabolic risk begins at BMI 23 in Indians, not 25.",
        "hi": "एशियन भारतीयों में समान BMI पर पश्चिमी लोगों की तुलना में अधिक शरीर में वसा होती है। भारतीयों में BMI 23 से चयापचय जोखिम शुरू होता है, 25 से नहीं।",
    },
    "colour_guide": {
        "en": "Green = eat freely | Orange = moderate | Red = restrict for all T2DM patients",
        "hi": "हरा = स्वतंत्र रूप से खाएं | नारंगी = सीमित मात्रा | लाल = सभी मधुमेह रोगियों के लिए परहेज़",
    },
    "disclaimer": {
        "en": "This diet guide is prepared for use by trained medical professionals. These charts are clinical starting points and must be individualized. Not a prescription — individual advice must be given by a qualified physician or registered dietitian after clinical assessment.",
        "hi": "यह आहार मार्गदर्शिका प्रशिक्षित चिकित्सा पेशेवरों के उपयोग के लिए है। ये चार्ट नैदानिक शुरुआती बिंदु हैं और व्यक्तिगत रूप से अनुकूलित किए जाने चाहिए। यह नुस्खा नहीं है — व्यक्तिगत सलाह एक योग्य चिकित्सक या पंजीकृत आहार विशेषज्ञ द्वारा दी जानी चाहिए।",
    },
    "individualization_factors": [
        {"en": "Current medications - especially insulin and sulfonylurea. Caloric restriction without dose adjustment risks hypoglycemia.",
         "hi": "वर्तमान दवाएं — विशेष रूप से इंसुलिन और सल्फोनीलयूरिया। खुराक समायोजन के बिना कैलोरी कम करने से हाइपोग्लाइसीमिया का जोखिम।"},
        {"en": "Renal function (eGFR) - protein restriction required if eGFR < 45 ml/min. High-protein plans do NOT apply to CKD Stage 3b+.",
         "hi": "गुर्दे की कार्यक्षमता (eGFR) — eGFR < 45 होने पर प्रोटीन कम करना ज़रूरी। उच्च प्रोटीन सुझाव CKD चरण 3b+ पर लागू नहीं।"},
        {"en": "Cardiac status - sodium restriction if heart failure; saturated fat modification if CAD or post-MI.",
         "hi": "हृदय स्थिति — हृदय विफलता में सोडियम कम करें; CAD या हृदयाघात के बाद संतृप्त वसा संशोधित करें।"},
        {"en": "Liver function - fatty liver patients may need modified fat intake and alcohol history review.",
         "hi": "यकृत कार्यक्षमता — फैटी लिवर रोगियों में वसा का सेवन संशोधित करना ज़रूरी हो सकता है।"},
        {"en": "Pregnancy - these charts do NOT apply to gestational diabetes. Use separate antenatal protocols.",
         "hi": "गर्भावस्था — ये चार्ट गर्भकालीन मधुमेह पर लागू नहीं होते। अलग प्रसवपूर्व प्रोटोकॉल का उपयोग करें।"},
        {"en": "Paediatric patients - caloric targets and portions differ significantly from adult guidelines.",
         "hi": "बाल रोगी — कैलोरी लक्ष्य और भोजन मात्रा वयस्क दिशानिर्देशों से काफी अलग हैं।"},
    ],
    "sources": "RSSDI Clinical Practice Guidelines 2017 - ICMR-NIN Dietary Guidelines 2024 - ADA Standards of Care 2024 - Indian Journal of Endocrinology & Metabolism (Asian BMI Consensus) - DiRECT Trial (Lean et al., Lancet 2018) - Joslin Diabetes Center Clinical Nutrition 2018",
}

# BMI classification is Asian-Indian specific (lower cutoffs than WHO).
BMI_GROUPS = {
    1: {
        "group_no": 1,
        "name": {"en": "Normal Weight T2DM", "hi": "सामान्य वज़न, मधुमेह"},
        "bmi_range": "18.5-22.9 kg/m2",
        "bmi_min": 18.5, "bmi_max": 22.9,
        "calorie_target": "1,600-1,800 kcal/day",
        "weight_goal": {"en": "Maintain", "hi": "वज़न बनाए रखें"},
        "key_focus": {"en": "Sugar control, prevent weight gain", "hi": "शुगर नियंत्रण, वज़न न बढ़ने दें"},
        "macros": {"carbs": "50-55% (200-240g)", "protein": "20-22% (80-100g)", "fat": "25-28% (45-55g)", "fibre": ">=25g/day"},
        "meal_times": [
            {"time": "6:30 am", "label": "", "en": "1 glass warm water + 6 soaked almonds + 2 walnuts (before any tea or food)",
             "hi": "1 गिलास गर्म पानी + 6 भीगे बादाम + 2 अखरोट (चाय या खाने से पहले)", "kcal": "~80"},
            {"time": "8:00 am", "label": "Breakfast", "en": "2 wheat roti (40g each) + 1 cup sabzi + 1 cup egg bhurji (2 eggs) OR paneer (50g) + 1 cup low-fat curd. No butter/ghee on roti.",
             "hi": "2 गेहूं रोटी + सब्ज़ी + 2 अंडे की भुर्जी या पनीर (50g) + दही। रोटी पर मक्खन/घी न लगाएं।", "kcal": "~380"},
            {"time": "10:30 am", "label": "Snack", "en": "1 small fruit: guava, apple or pear (150g) OR cucumber+tomato salad",
             "hi": "1 छोटा फल: अमरूद/सेब/नाशपाती या खीरा+टमाटर सलाद", "kcal": "~70"},
            {"time": "1:00 pm", "label": "Lunch", "en": "2 roti + 1 bowl mixed dal/rajma (150ml) + 1 cup sabzi + salad + 1 cup low-fat curd. Rice: max 1/2 cup cooked if needed.",
             "hi": "2 रोटी + दाल/राजमा + सब्ज़ी + सलाद + दही। चावल चाहिए तो 1/2 कटोरी पका हुआ।", "kcal": "~480"},
            {"time": "4:00 pm", "label": "Snack", "en": "Handful (30g) roasted chana OR 1 cup buttermilk OR 2 walnuts + 1 date",
             "hi": "मुट्ठी भर भुना चना या 1 गिलास छाछ या 2 अखरोट + 1 खजूर", "kcal": "~100"},
            {"time": "7:30 pm", "label": "Dinner", "en": "2 roti + 1 bowl dal/sabzi + 1 cup salad (lightest meal of day). No rice at dinner.",
             "hi": "2 रोटी + दाल/सब्ज़ी + सलाद (रात का खाना सबसे हल्का होना चाहिए)। रात को चावल नहीं।", "kcal": "~420"},
            {"time": "9:30 pm", "label": "Bedtime", "en": "1 glass warm low-fat milk (no sugar) OR haldi doodh",
             "hi": "1 गिलास गर्म कम चर्बी वाला दूध (बिना चीनी) या हल्दी वाला दूध", "kcal": "~80"},
        ],
        "recommended_foods": ["Daliya", "Methi (fenugreek)", "Karela (bitter gourd)", "Sprouts", "Green vegetables", "Dal", "Low-fat curd", "Wheat/multigrain roti"],
        "avoid_foods": ["Maida roti/naan", "White polished rice", "Sabudana", "Fruit juice", "Sugar in tea", "Fried namkeen/chips"],
        "strict_avoidance": [
            {"en": "Mithai, halwa, gulab jamun, ladoo - any time", "hi": "मिठाई, हलवा, गुलाब जामुन, लड्डू — कभी नहीं"},
            {"en": "Packaged biscuits, namkeen, mixture", "hi": "पैकेट बिस्किट, नमकीन, मिक्स्चर"},
            {"en": "Cold drinks, packaged juice, energy drinks", "hi": "कोल्ड ड्रिंक, पैकेट जूस, एनर्जी ड्रिंक"},
            {"en": "Puri, bhatura, deep-fried paratha", "hi": "पूरी, भटूरा, डीप फ्राई पराठा"},
            {"en": "Alcohol in any form", "hi": "शराब किसी भी रूप में"},
            {"en": "Maida in any form: bread, pasta, naan", "hi": "मैदा किसी भी रूप में: ब्रेड, पास्ता, नान"},
        ],
        "special_advice": [
            {"en": "Eat every 3-4 hours. Never skip a meal.", "hi": "हर 3–4 घंटे में खाएं। खाना न छोड़ें।"},
            {"en": "Dinner before 8 pm.", "hi": "रात 8 बजे से पहले खाना खाएं।"},
            {"en": "Walk 20-30 min after every main meal, not before.", "hi": "हर मुख्य भोजन के 20–30 मिनट बाद टहलें।"},
            {"en": "Drink 8-10 glasses water/day.", "hi": "रोज़ 8–10 गिलास पानी पिएं।"},
            {"en": "Use a katori (small bowl) for portion control.", "hi": "छोटी कटोरी और थाली का उपयोग करें।"},
            {"en": "Cook in mustard or groundnut oil. Max 2 tsp per meal.", "hi": "सरसों या मूंगफली के तेल में पकाएं। तेल नापें — अधिकतम 2 छोटी चम्मच।"},
        ],
        "exercise": {"en": "30 min brisk walk daily, morning preferred", "hi": "रोज़ 30 मिनट तेज़ चाल, सुबह बेहतर"},
        "water_intake": {"en": "8-10 glasses daily", "hi": "8-10 गिलास प्रतिदिन"},
    },
    2: {
        "group_no": 2,
        "name": {"en": "Overweight T2DM", "hi": "अधिक वज़न, मधुमेह"},
        "bmi_range": "23.0-24.9 kg/m2",
        "bmi_min": 23.0, "bmi_max": 24.9,
        "calorie_target": "1,400-1,600 kcal/day",
        "weight_goal": {"en": "-3 to 5% in 3 months", "hi": "3 महीने में 3–5% घटाएं"},
        "key_focus": {"en": "Mild deficit, reduce visceral fat", "hi": "हल्की कमी, पेट की चर्बी घटाएं"},
        "macros": {"carbs": "45-50% (158-200g)", "protein": "22-25% (78-100g)", "fat": "25-28% (39-50g)", "fibre": ">=28g/day"},
        "meal_times": [
            {"time": "6:30 am", "label": "", "en": "1 glass warm water + 1/2 tsp soaked methi seeds + 5 almonds. Methi improves insulin sensitivity.",
             "hi": "1 गिलास गर्म पानी + 1/2 छोटी चम्मच भिगोई मेथी + 5 बादाम। मेथी इंसुलिन संवेदनशीलता बढ़ाती है।", "kcal": "~60"},
            {"time": "8:00 am", "label": "Breakfast", "en": "1.5 roti + 1 cup sabzi + 1 egg (boiled/poached) + 1/2 cup low-fat curd OR vegetable daliya + 1 boiled egg. Reduce to 1 roti if post-meal sugar >180.",
             "hi": "1.5 रोटी + सब्ज़ी + 1 उबला अंडा + दही या सब्ज़ी दलिया + उबला अंडा। शुगर 180 से ज़्यादा हो तो 1 रोटी करें।", "kcal": "~340"},
            {"time": "11:00 am", "label": "Snack", "en": "1 cup buttermilk (no sugar) OR 10 makhana dry-roasted OR 1/2 cup sprouts",
             "hi": "छाछ (बिना चीनी) या 10 भुना मखाना या 1/2 कटोरी अंकुरित अनाज", "kcal": "~60"},
            {"time": "1:00 pm", "label": "Lunch", "en": "1.5 roti + 1 bowl dal (100ml) + 2 cups sabzi + large salad + 1/2 cup low-fat curd. Rice only if HbA1c <7, max 1/4 cup cooked. Fill half plate with vegetables first.",
             "hi": "1.5 रोटी + दाल + 2 कटोरी सब्ज़ी + सलाद + दही। HbA1c <7 हो तो 1/4 कटोरी चावल।", "kcal": "~420"},
            {"time": "4:00 pm", "label": "Snack", "en": "1 whole cucumber/carrot (raw) + 1 cup plain green tea (no sugar)",
             "hi": "1 खीरा/गाजर (कच्चा) + 1 कप बिना चीनी ग्रीन टी", "kcal": "~40"},
            {"time": "7:00 pm", "label": "Dinner", "en": "1.5 roti + 1 cup dal/sabzi + 2 cups salad. No rice at dinner. Finish by 7:30 pm.",
             "hi": "1.5 रोटी + दाल/सब्ज़ी + सलाद। रात में चावल नहीं। 7:30 बजे तक खाना खत्म करें।", "kcal": "~360"},
            {"time": "9:00 pm", "label": "Bedtime", "en": "1 cup warm low-fat milk with pinch turmeric + cinnamon (no sugar)",
             "hi": "1 कप गर्म कम चर्बी वाला दूध + हल्दी + दालचीनी (बिना चीनी)", "kcal": "~70"},
        ],
        "recommended_foods": ["Jowar/bajra roti", "Methi seeds (soaked overnight)", "Low-fat dahi", "Sprouts", "Non-starchy sabzi", "Cinnamon (daalchini)"],
        "avoid_foods": ["2 roti per meal (reduce to 1.5)", "Sugary chai", "Full-cream dahi", "Ghee/butter paratha", "Rava upma", "Rajma-chawal full portion"],
        "strict_avoidance": [
            {"en": "Rice at dinner - completely removed for this group", "hi": "रात के खाने में चावल — इस समूह के लिए पूरी तरह हटाया गया"},
            {"en": "All fried foods: puri, bhatura, pakora, samosa", "hi": "सभी तले खाद्य पदार्थ: पूरी, भटूरा, पकोड़ा, समोसा"},
            {"en": "Sweetened lassi, shrikhand, rabri, kheer", "hi": "मीठी लस्सी, श्रीखंड, रबड़ी, खीर"},
            {"en": "Dry fruits in excess: raisins, cashews >4/day, dates >1/day", "hi": "अत्यधिक मेवे: किशमिश, काजू >4/दिन, खजूर >1/दिन"},
            {"en": "Fruit juice of any kind", "hi": "किसी भी प्रकार का फलों का रस"},
            {"en": "Packaged foods with >5g sugar per 100g", "hi": "100g में >5g चीनी वाले पैकेट उत्पाद"},
        ],
        "special_advice": [
            {"en": "500 kcal/day deficit = ~0.5 kg/week weight loss, achieved without starvation.", "hi": "500 कैलोरी/दिन कम = ~0.5 किलो/सप्ताह वज़न घटाव।"},
            {"en": "Eat dinner 2-3 hours before sleep.", "hi": "सोने से 2–3 घंटे पहले रात का खाना खाएं।"},
            {"en": "Methi seeds soaked overnight reduce post-meal glucose by 10-15% over 6 weeks.", "hi": "रात भर भिगोई मेथी 6 हफ्तों में खाने के बाद शुगर 10–15% कम करती है।"},
            {"en": "Cinnamon 1/4 tsp daily in milk has modest HbA1c benefit.", "hi": "रोज़ दूध में 1/4 चम्मच दालचीनी से HbA1c में हल्का सुधार।"},
            {"en": "Avoid fruit at dinner.", "hi": "रात के खाने में फल न खाएं।"},
            {"en": "Weigh yourself weekly, same time each morning - not daily.", "hi": "हर सप्ताह सुबह एक ही समय पर वज़न करें — रोज़ नहीं।"},
        ],
        "exercise": {"en": "30 min brisk walk daily + light yoga if possible", "hi": "रोज़ 30 मिनट तेज़ चाल + हल्का योग"},
        "water_intake": {"en": "8-10 glasses daily", "hi": "8-10 गिलास प्रतिदिन"},
    },
    3: {
        "group_no": 3,
        "name": {"en": "Obese Class I T2DM", "hi": "मोटापा श्रेणी-1, मधुमेह"},
        "bmi_range": "25.0-27.4 kg/m2",
        "bmi_min": 25.0, "bmi_max": 27.4,
        "calorie_target": "1,200-1,400 kcal/day",
        "weight_goal": {"en": "-5 to 10% in 3-6 months", "hi": "3–6 महीने में 5–10% घटाएं"},
        "key_focus": {"en": "500 kcal deficit; millets; higher protein", "hi": "500 kcal कमी; मोटे अनाज; प्रोटीन ज़्यादा"},
        "macros": {"carbs": "40-45% (120-158g)", "protein": "25-28% (90-110g)", "fat": "28-30% (37-47g)", "fibre": ">=30g/day"},
        "meal_times": [
            {"time": "6:30 am", "label": "", "en": "1 glass warm water + 1 tsp soaked methi + 1/2 tsp jeera water. Cumin water improves fasting sugar over 8 weeks.",
             "hi": "1 गिलास गर्म पानी + 1 चम्मच भिगोई मेथी + 1/2 चम्मच जीरा पानी", "kcal": "~10"},
            {"time": "7:30 am", "label": "Breakfast", "en": "1 roti (jowar/bajra) + palak-paneer (50g low-fat) OR 3 egg whites bhurji + 1/2 cup low-fat curd + 1/2 cup raw salad. Protein at breakfast reduces cravings until lunch.",
             "hi": "1 जोवार/बाजरे की रोटी + पालक-पनीर (50g) या 3 अंडे की सफेदी की भुर्जी + दही + सलाद", "kcal": "~320"},
            {"time": "10:30 am", "label": "Snack", "en": "1 cup cucumber/tomato salad with lemon + 1 cup green tea OR plain chaach (no sugar)",
             "hi": "खीरा+टमाटर सलाद + नींबू + ग्रीन टी या सादी छाछ (बिना चीनी)", "kcal": "~40"},
            {"time": "1:00 pm", "label": "Lunch", "en": "1.5 roti + 1.5 cup moong+masoor dal (200ml) + 2 cups non-starchy sabzi + large salad. No rice. Moong+masoor dal = highest protein of all lentils.",
             "hi": "1.5 रोटी + मूंग+मसूर दाल + 2 कटोरी सब्ज़ी + सलाद। चावल नहीं।", "kcal": "~440"},
            {"time": "4:00 pm", "label": "Snack", "en": "1/2 cup sprouts (moong, chana) raw or lightly steamed + water or green tea. NO fruit between meals.",
             "hi": "1/2 कटोरी अंकुरित मूंग/चना + पानी/ग्रीन टी। भोजन के बीच फल नहीं।", "kcal": "~80"},
            {"time": "7:00 pm", "label": "Dinner", "en": "1 roti (bajra/jowar) + 1 cup thin moong dal + 2 cups salad/steamed sabzi. No starchy vegetables. Finish by 7 pm.",
             "hi": "1 बाजरे/जोवार की रोटी + पतली मूंग दाल + सब्ज़ी/सलाद। आलू-गाजर नहीं। शाम 7 बजे तक खाना।", "kcal": "~300"},
            {"time": "9:00 pm", "label": "Bedtime", "en": "1 cup warm skimmed milk with 1/4 tsp turmeric + 1/4 tsp cinnamon. No sugar. Or warm water only.",
             "hi": "1 कप गर्म स्किम्ड दूध + हल्दी + दालचीनी, बिना चीनी। या सादा गर्म पानी।", "kcal": "~50"},
        ],
        "recommended_foods": ["Jowar/bajra/ragi roti", "Moong+masoor dal", "Non-starchy sabzi (lauki, turai, parwal, tinda) - unlimited", "3 egg whites", "Tofu/low-fat paneer"],
        "avoid_foods": ["Ghee tadka on dal", "Aloo paratha", "3 roti per meal", "Full-fat paneer", "Any rice (even brown)", "Chole bhature"],
        "strict_avoidance": [
            {"en": "Rice - completely eliminated for this group", "hi": "चावल — इस समूह के लिए पूरी तरह हटाया गया"},
            {"en": "Potatoes in any form", "hi": "किसी भी रूप में आलू"},
            {"en": "All deep-fried foods without exception", "hi": "सभी डीप फ्राई खाद्य पदार्थ, कोई अपवाद नहीं"},
            {"en": "Full-fat dairy - low-fat/skimmed only", "hi": "पूर्ण वसा डेयरी — सिर्फ कम चर्बी/स्किम्ड उपयोग करें"},
            {"en": "All sugar, jaggery, honey without exception", "hi": "सभी चीनी, गुड़, शहद — बिना किसी अपवाद के"},
            {"en": "Fruit between meals - only at 4pm snack slot", "hi": "भोजन के बीच फल (केवल शाम 4 बजे के स्नैक में)"},
        ],
        "special_advice": [
            {"en": "This group needs 500-700 kcal deficit daily. Target 5-7% loss in 12 weeks to see HbA1c improvement.", "hi": "इस समूह को रोज़ 500–700 कैलोरी कम चाहिए। 12 हफ्तों में 5–7% वज़न घटाने से HbA1c में सुधार दिखेगा।"},
            {"en": "Protein target is higher - 90-110g/day prevents muscle loss during caloric restriction.", "hi": "यहाँ प्रोटीन लक्ष्य ज़्यादा है — 90–110g/दिन मांसपेशियों को बचाता है।"},
            {"en": "Millets (jowar, bajra, ragi) are ideal - low GI, high satiety.", "hi": "मोटे अनाज (जोवार, बाजरा, रागी) आदर्श हैं — कम GI, अधिक तृप्ति।"},
            {"en": "Non-starchy vegetables are unlimited.", "hi": "गैर-स्टार्चयुक्त सब्ज़ियाँ असीमित हैं।"},
            {"en": "Intermittent eating window 8 am - 7 pm (11-hour) is particularly effective.", "hi": "खाने की खिड़की सुबह 8 बजे से रात 7 बजे (11 घंटे) विशेष रूप से प्रभावी है।"},
            {"en": "Strength exercises 3x/week (squats, wall push-ups) preserves muscle.", "hi": "सप्ताह में 3 बार शक्ति व्यायाम (स्क्वाट, दीवार पर पुश-अप)।"},
        ],
        "exercise": {"en": "30 min walk + strength exercises 3x/week (squats, wall push-ups)", "hi": "30 मिनट टहलना + सप्ताह में 3 बार शक्ति व्यायाम"},
        "water_intake": {"en": "8-10 glasses daily", "hi": "8-10 गिलास प्रतिदिन"},
    },
    4: {
        "group_no": 4,
        "name": {"en": "Obese Class II+ T2DM", "hi": "मोटापा श्रेणी-2+, मधुमेह"},
        "bmi_range": ">=27.5 kg/m2",
        "bmi_min": 27.5, "bmi_max": 999,
        "calorie_target": "1,000-1,200 kcal/day",
        "weight_goal": {"en": "-10 to 15% - remission possible", "hi": "10–15% घटाएं — रिमिशन संभव"},
        "key_focus": {"en": "Remission possible - strict protocol", "hi": "रिमिशन संभव — सख्त प्रोटोकॉल"},
        "macros": {"carbs": "35-40% (88-120g)", "protein": "28-30% (105-120g)", "fat": "30-32% (33-43g)", "fibre": ">=35g/day"},
        "meal_times": [
            {"time": "6:30 am", "label": "", "en": "2 glasses warm water + 1 tsp soaked methi + 1/2 tsp cinnamon powder in water. Do not skip on medication - prevents hypoglycemia.",
             "hi": "2 गिलास गर्म पानी + भिगोई मेथी + दालचीनी पानी। दवाई पर हैं तो यह ज़रूर लें।", "kcal": "~10"},
            {"time": "7:30 am", "label": "Breakfast", "en": "3 egg whites (boiled/omelette, no yolk, no oil) + 1 jowar/bajra roti (40g) + 1/2 cup low-fat curd + 1/2 cup raw salad. Veg option: 100g low-fat paneer bhurji (dry, no oil) + 1 roti.",
             "hi": "3 अंडे की सफेदी + 1 जोवार/बाजरे की रोटी + दही + सलाद। शाकाहारी: 100g कम चर्बी पनीर भुर्जी + 1 रोटी", "kcal": "~280"},
            {"time": "10:30 am", "label": "Snack", "en": "1 cup plain buttermilk + 10 roasted makhana OR 1/2 cup boiled sprouts. Nothing else.",
             "hi": "सादी छाछ + 10 भुना मखाना या उबले अंकुरित अनाज। बस यही।", "kcal": "~80"},
            {"time": "1:00 pm", "label": "Lunch", "en": "1 multigrain roti (40g) + 2 cups moong/masoor/chana dal (200ml) + 2 cups non-starchy sabzi + large salad + 1/2 cup low-fat curd. ZERO rice. Eat salad first, then dal, then roti last.",
             "hi": "1 मल्टीग्रेन रोटी + मूंग/मसूर/चना दाल + 2 कटोरी सब्ज़ी + सलाद + दही। चावल बिल्कुल नहीं। पहले सलाद, फिर दाल, फिर रोटी।", "kcal": "~380"},
            {"time": "4:00 pm", "label": "Snack", "en": "1 cup green tea/jeera water + 1 small fruit (guava 100g OR 1/2 apple OR 1/2 pear). Fruit only at this time.",
             "hi": "ग्रीन टी + 1 छोटा फल (अमरूद/आधा सेब/आधी नाशपाती)। फल सिर्फ इसी समय।", "kcal": "~70"},
            {"time": "7:00 pm", "label": "Dinner", "en": "1 small roti (30g, bajra/jowar) + 1.5 cup thin moong dal or palak-dal soup + 2 cups salad. Finish by 6:45 pm ideally.",
             "hi": "1 छोटी बाजरे/जोवार की रोटी + पतली मूंग दाल सूप + सलाद। आदर्शतः शाम 6:45 तक खाना खत्म।", "kcal": "~260"},
            {"time": "8:30 pm", "label": "Bedtime", "en": "1 glass warm water with 1/4 tsp turmeric + 1/4 tsp cinnamon. Milk only if sugar <80 mg/dL.",
             "hi": "गर्म हल्दी-दालचीनी पानी। दूध तभी लें जब शुगर 80 mg/dL से कम हो।", "kcal": "~5"},
        ],
        "recommended_foods": ["Jowar/bajra/ragi roti exclusively", "Egg whites", "Tofu / low-fat paneer", "Non-starchy sabzi (unlimited)", "Moong/masoor/chana dal"],
        "avoid_foods": ["2-3 roti per meal", "Any rice at all", "Full-fat paneer", "Ghee tadka on dal", "Sabzi cooked in excess oil", "Sweet milk chai"],
        "strict_avoidance": [
            {"en": "Rice, bread, naan, bhatura, puri - completely removed", "hi": "चावल, ब्रेड, नान, भटूरा, पूरी — पूरी तरह हटाए गए"},
            {"en": "All dairy with >1.5% fat - skimmed only", "hi": "1.5% से ज़्यादा वसा वाले सभी डेयरी उत्पाद — केवल स्किम्ड"},
            {"en": "Sugar, jaggery, honey, date syrup - any form", "hi": "चीनी, गुड़, शहद, खजूर का शरबत — किसी भी रूप में"},
            {"en": "Aloo, shakarkandi, arbi - no starchy root vegetables", "hi": "आलू, शकरकंदी, अरबी — कोई भी स्टार्चयुक्त जड़ वाली सब्ज़ी"},
            {"en": "All deep-fried food, street food", "hi": "सभी डीप फ्राई खाना, स्ट्रीट फूड"},
            {"en": "Nuts beyond 4 almonds/day", "hi": "4 बादाम/दिन से ज़्यादा मेवे"},
            {"en": "All packaged/processed foods", "hi": "सभी पैकेट / प्रोसेस्ड खाद्य पदार्थ"},
        ],
        "special_advice": [
            {"en": "CRITICAL: If on insulin or sulfonylurea (glibenclamide), do NOT go below 1,000 kcal without doctor review - real hypoglycemia risk.", "hi": "⚠ महत्वपूर्ण: इंसुलिन या सल्फोनीलयूरिया पर हैं तो डॉक्टर की समीक्षा के बिना 1000 कैलोरी से नीचे न जाएं।"},
            {"en": "DiRECT trial: 10-15% weight loss achieves T2DM remission in 40-50% of patients at this BMI.", "hi": "DiRECT परीक्षण: 10–15% वज़न घटाने से इस BMI पर 40–50% रोगियों में मधुमेह रिमिशन होता है।"},
            {"en": "Eat in sequence every meal: salad/raw first, then dal/protein, then roti last. Reduces post-meal glucose 15-20%.", "hi": "हर भोजन में क्रम अपनाएं: पहले सलाद/कच्चा, फिर दाल/प्रोटीन, अंत में रोटी।"},
            {"en": "500ml water 30 min before each main meal reduces meal intake by ~15%.", "hi": "हर मुख्य भोजन से 30 मिनट पहले 500ml पानी भोजन का सेवन ~15% कम करता है।"},
            {"en": "Sleep 7-8 hours. Sleep deprivation raises cortisol and fasting glucose.", "hi": "7–8 घंटे सोएं। नींद की कमी कोर्टिसोल और खाली पेट शुगर बढ़ाती है।"},
            {"en": "Waist circumference target: Men <90 cm, Women <80 cm. Measure monthly.", "hi": "कमर की माप लक्ष्य: पुरुष <90 सेमी, महिलाएं <80 सेमी। मासिक मापें।"},
        ],
        "exercise": {"en": "30 min walk daily (as tolerated) + hydration/sleep discipline", "hi": "रोज़ 30 मिनट टहलना (सहनशक्ति अनुसार) + पानी/नींद अनुशासन"},
        "water_intake": {"en": "8-10 glasses daily, 500ml before meals", "hi": "8-10 गिलास प्रतिदिन, भोजन से पहले 500ml"},
    },
}

# Master substitution table — usable across all groups.
MASTER_SUBSTITUTIONS = [
    {"original": {"en": "White rice (1 cup cooked)", "hi": "सफेद चावल (1 कप पका)"}, "gi": "72", "kcal": 200,
     "replace_with": {"en": "Brown rice 3/4 cup OR jowar roti 1", "hi": "ब्राउन राइस 3/4 कप या जोवार रोटी 1"}, "saves": "-60 kcal"},
    {"original": {"en": "Maida roti / naan", "hi": "मैदे की रोटी / नान"}, "gi": "70", "kcal": 200,
     "replace_with": {"en": "Whole wheat roti (gehun atta) 1 piece", "hi": "गेहूं की रोटी 1"}, "saves": "-10 kcal, +3g fibre"},
    {"original": {"en": "Atta paratha + ghee", "hi": "आटे का पराठा + घी"}, "gi": "55", "kcal": 280,
     "replace_with": {"en": "Plain multigrain dry-roasted roti", "hi": "सादी मल्टीग्रेन रोटी (सूखी भुनी)"}, "saves": "-160 kcal"},
    {"original": {"en": "Sabudana khichdi (1 cup)", "hi": "साबूदाना खिचड़ी"}, "gi": "80", "kcal": 350,
     "replace_with": {"en": "Daliya khichdi (1 cup)", "hi": "दलिया खिचड़ी"}, "saves": "-130 kcal"},
    {"original": {"en": "Sooji/rava upma", "hi": "सूजी/रवा उपमा"}, "gi": "65", "kcal": 250,
     "replace_with": {"en": "Daliya upma OR oats upma", "hi": "दलिया उपमा या ओट्स उपमा"}, "saves": "-40 kcal"},
    {"original": {"en": "Poha (1 cup)", "hi": "पोहा (1 कप)"}, "gi": "74", "kcal": 244,
     "replace_with": {"en": "Oats poha with vegetables", "hi": "ओट्स पोहा + सब्ज़ियाँ"}, "saves": "-30 kcal"},
    {"original": {"en": "Aloo sabzi (1 cup)", "hi": "आलू की सब्ज़ी"}, "gi": "78 (potato)", "kcal": 150,
     "replace_with": {"en": "Lauki / turai / tinda sabzi", "hi": "लौकी / तुरई / टिंडा सब्ज़ी"}, "saves": "-50 kcal"},
    {"original": {"en": "Full-fat paneer (100g)", "hi": "पूर्ण वसा पनीर"}, "gi": "7", "kcal": 320,
     "replace_with": {"en": "Low-fat paneer 50g + tofu 50g", "hi": "कम चर्बी पनीर 50g + टोफू 50g"}, "saves": "-140 kcal"},
    {"original": {"en": "Whole milk, 1 glass (250ml)", "hi": "पूर्ण दूध 1 गिलास"}, "gi": "30", "kcal": 165,
     "replace_with": {"en": "Toned / low-fat milk 1 glass", "hi": "टोंड / कम चर्बी दूध 1 गिलास"}, "saves": "-55 kcal"},
    {"original": {"en": "Sweet lassi (250ml)", "hi": "मीठी लस्सी"}, "gi": "35", "kcal": 300,
     "replace_with": {"en": "Plain chaach / buttermilk (250ml)", "hi": "सादी छाछ"}, "saves": "-265 kcal"},
    {"original": {"en": "Chai: 2 tsp sugar + milk", "hi": "चाय: 2 चम्मच चीनी + दूध"}, "gi": "65+", "kcal": 120,
     "replace_with": {"en": "No sugar + toned milk OR green tea", "hi": "बिना चीनी चाय + टोंड दूध या ग्रीन टी"}, "saves": "-100 kcal/cup"},
    {"original": {"en": "Banana (1 medium)", "hi": "केला (1 मध्यम)"}, "gi": "52", "kcal": 105,
     "replace_with": {"en": "Guava 1 medium (150g)", "hi": "अमरूद 1 मध्यम"}, "saves": "-45 kcal, +2g fibre"},
    {"original": {"en": "Mango, 1 slice (100g)", "hi": "आम 1 टुकड़ा"}, "gi": "55", "kcal": 60,
     "replace_with": {"en": "Apple 1/2 OR pear 1/2 (100g)", "hi": "सेब 1/2 या नाशपाती 1/2"}, "saves": "-5 kcal, +1g fibre"},
    {"original": {"en": "Fruit juice (1 glass)", "hi": "फलों का रस"}, "gi": "70+", "kcal": 150,
     "replace_with": {"en": "Whole fruit (150g)", "hi": "पूरा फल खाएं"}, "saves": "-80 kcal, +5g fibre"},
    {"original": {"en": "Ghee (1 tsp) in dal/roti", "hi": "दाल/रोटी में घी 1 चम्मच"}, "gi": "-", "kcal": 45,
     "replace_with": {"en": "Mustard oil 1/2 tsp for tadka only", "hi": "सरसों तेल 1/2 चम्मच सिर्फ तड़के के लिए"}, "saves": "-25 kcal"},
    {"original": {"en": "Namkeen / mixture (30g)", "hi": "नमकीन / मिक्स्चर"}, "gi": "60", "kcal": 150,
     "replace_with": {"en": "10 roasted makhana OR 1 cup plain chaach", "hi": "10 भुना मखाना या 1 कप सादी छाछ"}, "saves": "-115 kcal"},
    {"original": {"en": "Deep-fried pakora (2 pieces)", "hi": "डीप फ्राई पकोड़ा"}, "gi": "55", "kcal": 200,
     "replace_with": {"en": "Baked/air-fried besan chilla (2 small)", "hi": "बेसन चीला (बेक/एयर फ्राई)"}, "saves": "-120 kcal"},
    {"original": {"en": "Cold drink/soft drink (300ml)", "hi": "कोल्ड ड्रिंक / सोडा"}, "gi": "65", "kcal": 130,
     "replace_with": {"en": "Nimbu pani (no sugar) OR plain water", "hi": "बिना चीनी नींबू पानी या सादा पानी"}, "saves": "-130 kcal, 8 tsp sugar"},
]

# Glycemic Index chart, grouped by food category, for quick reference.
GI_CHART = {
    "legend": {
        "en": "GI < 55 = Eat freely | 55-69 = Moderate | >=70 = Restrict/Avoid",
        "hi": "GI < 55 = स्वतंत्र रूप से खाएं | 55–69 = सीमित मात्रा | >=70 = परहेज़ करें",
    },
    "categories": {
        "Grains & Cereals": [
            {"food": "Jowar roti", "gi": 55}, {"food": "Bajra roti", "gi": 54}, {"food": "Ragi roti", "gi": 68},
            {"food": "Wheat roti", "gi": 49}, {"food": "Brown rice", "gi": 55}, {"food": "White rice", "gi": 72},
        ],
        "Processed Grains": [
            {"food": "Daliya", "gi": 41}, {"food": "Oats (rolled)", "gi": 55}, {"food": "Sooji/rava", "gi": 65},
            {"food": "Poha", "gi": 74}, {"food": "Sabudana", "gi": 80}, {"food": "Maida", "gi": 70},
        ],
        "Lentils & Legumes": [
            {"food": "Moong dal", "gi": 32}, {"food": "Masoor dal", "gi": 31}, {"food": "Chana dal", "gi": 11},
            {"food": "Rajma", "gi": 29}, {"food": "Chole", "gi": 33}, {"food": "Arhar dal", "gi": 22},
        ],
        "Fruits": [
            {"food": "Jamun", "gi": 25}, {"food": "Guava", "gi": 31}, {"food": "Apple", "gi": 38},
            {"food": "Pear", "gi": 38}, {"food": "Orange", "gi": 43}, {"food": "Mango", "gi": 55},
        ],
        "Snacks": [
            {"food": "Makhana", "gi": 14}, {"food": "Roast chana", "gi": 28}, {"food": "Sprouts", "gi": 25},
            {"food": "Almonds", "gi": 0}, {"food": "Namkeen", "gi": 60}, {"food": "Biscuit", "gi": 70},
        ],
        "Vegetables": [
            {"food": "Lauki", "gi": 25}, {"food": "Turai", "gi": 28}, {"food": "Palak", "gi": 15},
            {"food": "Tomato", "gi": 15}, {"food": "Aloo", "gi": 78}, {"food": "Beetroot", "gi": 64},
        ],
    },
}


def get_bmi_group(bmi: float) -> int:
    """Return the Asian-Indian BMI group number (1-4) for T2DM diet planning."""
    if bmi is None:
        return 1
    if bmi < 23.0:
        return 1
    if bmi < 25.0:
        return 2
    if bmi < 27.5:
        return 3
    return 4


def compute_bmi(weight_kg, height_cm):
    if not weight_kg or not height_cm:
        return None
    h_m = height_cm / 100.0
    if h_m <= 0:
        return None
    return round(weight_kg / (h_m * h_m), 1)


def group_summary(group_no: int) -> dict:
    """A slim summary of one BMI group, for list views."""
    g = BMI_GROUPS.get(group_no)
    if not g:
        return {}
    return {
        "group_no": g["group_no"], "name": g["name"], "bmi_range": g["bmi_range"],
        "calorie_target": g["calorie_target"], "weight_goal": g["weight_goal"], "key_focus": g["key_focus"],
    }
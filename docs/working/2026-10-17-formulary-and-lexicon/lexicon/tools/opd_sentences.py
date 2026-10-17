"""300+ ordinary OPD dictation sentences (no new brand on purpose; some carry long-known drugs)."""
_BASE = """
Patient complains of fever for 3 days with body ache
Chest pain since morning, radiating to left arm
Take twice daily after food for five days
Take once at night before sleeping
Take on empty stomach early morning
Before breakfast with a glass of water
Follow up after 5 days with reports
Review after one week
BP check every morning and evening
Sugar fasting and post prandial tomorrow
Take with plenty of water
Avoid oily and spicy food
Drink warm water and take steam inhalation
Gargle with warm salt water thrice daily
Apply the cream locally twice a day
Continue the same medicines for one month
Stop if rash or itching appears
Come back if fever persists beyond three days
Headache on and off for two weeks
Cough with sputum since last week
Dry cough worse at night
Loose motions four times since yesterday
Vomiting twice since morning
Burning micturition for two days
Pain abdomen after meals
Acidity and bloating after dinner
Knee pain while climbing stairs
Lower back pain since lifting weight
Neck pain and stiffness in the morning
Giddiness on standing up suddenly
Breathlessness on exertion
Palpitations off and on
Swelling of both feet in the evening
Weakness and tiredness for a month
Loss of appetite and weight loss
Sleep disturbed due to pain
Joint pain in fingers in the morning
Itching all over the body at night
Red eyes with watering since yesterday
Ear pain and discharge from right ear
Sore throat with difficulty in swallowing
Runny nose and sneezing in the morning
Blocked nose and headache
Mild fever with chills in the evening
High grade fever with shivering
Temperature one hundred and two
Pulse is normal and regular
Blood pressure one forty by ninety
Oxygen saturation ninety eight percent on room air
Chest is clear on auscultation
Abdomen soft and non tender
No pallor no icterus no cyanosis
Advised complete blood count and urine routine
Advised liver function test and kidney function test
Advised thyroid profile and lipid profile
Advised chest x ray and ECG
Advised ultrasound abdomen
Get HbA1c done next visit
Check random blood sugar at home
Monitor blood pressure daily and maintain a chart
Walk for thirty minutes every day
Reduce salt intake in diet
Avoid sugar and sweets
Eat small frequent meals
Do not skip breakfast
Take adequate rest for three days
Drink at least three litres of water daily
Avoid cold drinks and ice cream
Wash hands before meals
Use a clean towel and keep the area dry
Keep the wound clean and dry
Change the dressing every alternate day
Come for dressing after two days
Suture removal after seven days
Physiotherapy for two weeks
Hot fomentation twice daily
Ice pack application for swelling
Elevate the leg while sleeping
Use a knee cap while walking
Avoid lifting heavy weights
Sit straight and avoid long sitting
Take the tablet half an hour before food
Take the capsule after breakfast
Take the syrup two teaspoons thrice daily
Two puffs of the inhaler when needed
Put two drops in each eye four times a day
Put drops in the ear three times a day
Dissolve the sachet in one glass of water
Take one tablet only if pain is severe
Take one tablet at bedtime
One tablet in the morning and one at night
Half tablet in the morning
Continue for three months and then review
Taper the dose over one week
Do not stop the medicine suddenly
Bring all old prescriptions next time
Bring the reports on the next visit
Next visit after fifteen days
Next review on Monday morning
Review on Friday with sugar reports
Child has fever and cold since two days
Child is not eating properly
Child weight is twelve kilograms
Give syrup five ml three times a day
Give plenty of fluids to the child
Steam inhalation for the child twice daily
Mother says the child cries at night
Pregnant patient, second trimester, routine check up
Advised iron and calcium supplements
Advised folic acid daily
Last menstrual period was on the fifth
Periods are irregular since six months
White discharge since one month
Pain during periods
Old patient with diabetes and hypertension for ten years
Known case of asthma since childhood
Known case of thyroid on treatment
History of heart attack two years ago
No known drug allergies
Allergic to sulpha drugs
Smoker for twenty years, advised to quit
Alcohol occasionally, advised to stop
Patient is anxious and not sleeping well
Counselled about diet and exercise
Explained the condition to the patient and relatives
Patient and attendant counselled
Referred to cardiologist for further evaluation
Referred to eye specialist
Referred to the surgeon for opinion
Admit if vomiting continues
Emergency if chest pain increases
Call immediately if breathing difficulty
Sugar is high today, increase the dose
BP is under control, continue the same
Weight is reduced by two kilograms
Patient feels better than before
Fever has come down since yesterday
Cough has reduced but not gone
Pain is better with the medicines
No improvement with the previous treatment
Side effects like nausea after the tablet
Stomach upset after taking the medicine
Constipation since starting the tablet
Patient has burning in the chest after food
Belching and gas after meals
Mouth ulcers since a week
Tooth pain on the right side
Bleeding gums while brushing
Dandruff and hair fall
Pimples on the face
Fungal infection in the groin
Cracked heels and dry skin
Dark circles and tired eyes
Blurred vision while reading
Ringing in the ears
Snoring at night
Daytime sleepiness
Frequent urination at night
Excessive thirst and hunger
Numbness in both feet
Tingling in the hands at night
Cramps in the legs at night
Sprain of the right ankle while walking
Fall from the bike, abrasion on the elbow
Dog bite yesterday, first dose given
Insect bite with swelling on the arm
Burns on the hand from hot water
Cut on the finger while cooking
Foreign body sensation in the eye
Nose bleed this morning
Hiccups since evening
Motion sickness while travelling
Dehydration due to loose motions
Heat stroke symptoms after working outside
Tired after night shift duty
Stress at work and headache
Exam stress and poor sleep
Old age weakness and joint pains
"""
_HINGLISH = """
bukhar teen din se hai
pet mein dard khane ke baad
sar dard subah se
khansi raat ko zyada hoti hai
khana khane ke baad dawa lena
subah khali pet lena
raat ko sone se pehle ek goli
paani zyada piyo
garam paani se gargle karo
thanda mat khao
din mein do baar lena
teen din baad dikhana
ulti aur dast subah se
kamar dard bahut hai
neend nahi aati
haath pair mein dard
chai kam piyo
roz subah walk karo
namak kam khao
cheeni band karo
"""
_DRUGS = ["paracetamol 650 mg", "dolo 650", "crocin 500 mg", "pan 40", "azithromycin 500 mg", "metformin 500 mg",
          "amlodipine 5 mg", "cetirizine 10 mg", "pantoprazole 40 mg", "atorvastatin 10 mg", "ondansetron 4 mg",
          "augmentin 625", "telmisartan 40 mg", "montelukast 10 mg", "vitamin d3 60000"]
_TIMING = ["twice daily after food for five days", "once at night", "before breakfast", "on empty stomach",
           "three times a day after meals", "when needed for pain", "once daily in the morning", "at bedtime for ten days"]
_PRE = ["tab", "tablet", "cap", "syrup"]


_CLINICAL = """
Tenderness in the epigastrium
Echo shows left atrium mildly dilated
Limited range of movement in the right shoulder
Ventral hernia, advised surgical opinion
Stone of 6 mm diameter in the right kidney
Blister on the left foot, keep it dry
Works in the garden, allergic rhinitis since spring
Bank employee with job stress
Skin grafting done last year
Proposal for surgery explained to the patient
Rumor of food poisoning in the hostel
Singular lesion on the scalp
"""


def _build():
    out = [s.strip() for s in (_BASE + _HINGLISH + _CLINICAL).splitlines() if s.strip()]
    combos = [f"{p} {d} {t}" for d in _DRUGS for t in _TIMING for p in _PRE]
    i = 0
    while len(out) < 320 and i < len(combos):
        s = combos[(i * 37) % len(combos)]
        if s not in out:
            out.append(s)
        i += 1
    return out


SENTENCES = _build()

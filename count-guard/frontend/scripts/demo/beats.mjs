// The one beat table behind the demo run and the demo document (spec P5). Strings were checked
// against the frontend and backend source; rulings P5-R5..R8 and R14 are applied.
export const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
export const ROLES = ["doctor", "nurse", "patient"];

export const MEDIA = {
  "kumar-orders.wav": "eval/p2",
  "kumar-paracetamol.wav": "eval/p2",
  "kumar-discharge.wav": "eval/p2",
  "rao-answer.wav": "eval/p2",
  "iyer-bp.wav": "eval/p2",
  "iyer-saline.wav": "eval/p2",
  "strip-paracetamol.png": "eval/p2",
  "tray-hernia.mp4": "eval/p3",
  "saline-setup.mp4": "eval/p3",
  "wound-day0.png": "eval/p4",
  "wound-day3.png": "eval/p4",
  "meds-iyer.png": "eval/p4",
};

export const GENERATOR = {
  "eval/p2": "eval/p2/make_media.py",
  "eval/p3": "eval/p3/make_clips.py",
  "eval/p4": "eval/p4/make_photos.py",
};

const SALINE = "Saline 1 litre over 2 hours, video check of the set-up";
const HEARD = "Heard by: Prepared demo result";
const DISCHARGE_BOXES = 'tick "Discharge card given", "Medicines handed over", "Reminders set"';

export const BEATS = [
  {
    id: "intro", path: "intro", role: "none", seconds: 3, film: true,
    say: "Count Guard is a research demo on a synthetic ward, running with no live model.",
    clicks: ["Open http://127.0.0.1:5273/", "Role Doctor"],
    expect: ["Models: offline (prepared results)", "Research demo. Not for clinical use."],
    keyed: "No model call. The header reads Models: live, not offline, when a key is set.",
  },
  {
    id: "das-rx", path: "das", role: "doctor", seconds: 5, film: true,
    say: "Dr. Rao opens Mr. Das, an outpatient, and loads the prescription for his clinic visit.",
    clicks: ["Chart A. Das", 'Button "Use the demo prescription"'],
    expect: ["In clinic", "Amlodipine"],
    keyed: "No model call.",
  },
  {
    id: "das-strip", path: "das", role: "doctor", seconds: 5, film: true,
    say: "A pharmacy strip is checked against the prescription, and the mismatch is named.",
    clicks: ['Field "One strip per line: name then strength" <- Amlodipine 10 mg', 'Button "Check these strips"'],
    expect: ["The prescription says Amlodipine 5 mg"],
    keyed: "No model call; this check is plain text matching.",
  },
  {
    id: "das-close", path: "das", role: "doctor", seconds: 3, film: true,
    say: "Dr. Rao closes the visit, and the record says nothing more is due.",
    clicks: ['Button "Close visit"'],
    expect: ["Clinic visit closed", "The visit is closed. No further steps."],
    keyed: "No model call.",
  },
  {
    id: "das-ask", path: "das", role: "patient", seconds: 12, film: true,
    say: "Mr. Das asks his own record about his tablet, and the answer comes from the record, with its source named.",
    clicks: ["Role Patient", "Pick A. Das", "Tab Ask", 'Textarea in "Ask the record" <- When do I take amlodipine?', 'Button "Ask the record"'],
    expect: ["Here is what your record says.", "Amlodipine", "Rules (no model)"],
    keyed: "1 Spark text call. The label reads Muse Spark in place of Rules (no model), and the answer is prose. No switch.",
  },
  {
    id: "das-mycare", path: "das", role: "patient", seconds: 6, film: true,
    say: "His My care page shows the closed visit in plain words.",
    clicks: ['Tab "My care"'],
    expect: ["Clinic visit closed"],
    absent: "\\b[a-z]+_[a-z_]+\\b|\\(seed\\)|undefined",
    keyed: "No model call.",
  },
  {
    id: "kumar-orders", path: "kumar", role: "doctor", seconds: 8, film: true,
    say: "Dr. Rao dictates admission orders for Mr. Kumar, and a draft appears with its source named.",
    clicks: ["Role Doctor", "Chart R. Kumar", 'Button "Use the demo prescription"', 'File eval/p2/kumar-orders.wav into "Dictate orders"'],
    expect: ["Draft from dictation · Rules (no model)", HEARD, "Paracetamol"],
    files: ["kumar-orders.wav"],
    keyed: "1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark; Heard by reads Muse Voice. Live speech can be replaced by Or type what was said.",
  },
  {
    id: "kumar-admit", path: "kumar", role: "doctor", seconds: 4, film: true,
    say: "Dr. Rao signs the orders and admits him; the screen says which nurse step comes next.",
    clicks: ['Button "Sign orders"', 'Button "Admit"'],
    expect: ["Being admitted", "Nurse acknowledges the new orders from Dr. A. Rao (synthetic), then completes the admission."],
    keyed: "No model call.",
  },
  {
    id: "kumar-admission", path: "kumar", role: "nurse", seconds: 6, film: true,
    say: "Nurse Meena sees the new orders in her queue, ticks the admission checks and acknowledges the orders.",
    clicks: ["Role Nurse", 'Tab "My queue"', "Chart R. Kumar", 'Tick "Wristband on", "Allergies checked", "Baseline observations taken", "Consent on file"', 'Button "Complete admission"', 'Button "Acknowledge"'],
    expect: ["New orders from Dr. A. Rao", "On the ward", "acknowledged the orders at"],
    before: ["New orders from Dr. A. Rao"],
    keyed: "No model call.",
  },
  {
    id: "kumar-theatre", path: "kumar", role: "doctor", seconds: 6, film: true,
    say: "Dr. Rao picks the hernia repair and sends him to theatre; the doctor's status follows.",
    clicks: ["Role Doctor", 'Select "Procedure" <- hernia-repair', 'Button "Send to theatre"'],
    expect: ["Swabs: 15", "In theatre", "Dr. A. Rao: In theatre with R. Kumar, free about"],
    before: ["Swabs: 15"],
    keyed: "No model call.",
  },
  {
    id: "kumar-chip", path: "kumar", role: "patient", seconds: 5, film: true,
    say: "Mr. Kumar's own Today page shows the doctor is in theatre with him.",
    clicks: ["Role Patient", "Pick R. Kumar", "Tab Today"],
    expect: ["In theatre with R. Kumar"],
    keyed: "No model call.",
  },
  {
    id: "kumar-free-soon", path: "kumar", role: "nurse", seconds: 0, film: false,
    say: "Check only: after the clock moves on one hour, the theatre chip reads expected free soon.",
    clicks: ["Role Nurse", "Chart R. Kumar", 'Button "+1 h" in "Demo clock"'],
    expect: ["In theatre with R. Kumar, expected free soon"],
    keyed: "No model call.",
  },
  {
    id: "kumar-tray", path: "kumar", role: "nurse", seconds: 6, film: true,
    say: "Nurse Asha films the tray; the check finds one needle holder missing and flags it for the surgeon.",
    clicks: ["Role Nurse", "Chart R. Kumar", 'File eval/p3/tray-hernia.mp4 into "Tray check"'],
    expect: ["Flagged: not everything planned was seen. The surgeon decides.", "needle holder", "2 (missing)", "Prepared demo result"],
    files: ["tray-hernia.mp4"],
    keyed: "SAM 3.1 video call (clip seconds, capped at 120 s). The label reads SAM 3.1. Switch: TRAY_LIVE. Run make cost CLIP=<file> for the bill.",
  },
  {
    id: "kumar-count", path: "kumar", role: "nurse", seconds: 9, film: true,
    say: "Surgery begins, the pack opens at 15 swabs, and a count of 14 is flagged until it is corrected to 15.",
    clicks: ['Button "Surgery began"', 'Button "Record pack opened" (prefilled 15)', 'Field "Closing count (returned)" <- 14', 'Button "Record closing count"', 'Field "Closing count (returned)" <- 15', 'Button "Correct the count"'],
    expect: ["Closing count: 14 of 15 back, 1 unaccounted.", "Correction recorded."],
    before: ["Closing count: 14 of 15 back, 1 unaccounted."],
    keyed: "No model call.",
  },
  {
    id: "kumar-back", path: "kumar", role: "nurse", seconds: 4, film: true,
    say: "Surgery ends and he returns to the ward; Dr. Rao shows as available again.",
    clicks: ['Button "Surgery ended"', 'Button "Back to ward"'],
    expect: ["On the ward", "Dr. A. Rao: Available"],
    keyed: "No model call.",
  },
  {
    id: "kumar-paracetamol", path: "kumar", role: "nurse", seconds: 7, film: true,
    say: "Nurse Meena records the paracetamol round by voice, adds the strip photo, and confirms.",
    clicks: ['File eval/p2/kumar-paracetamol.wav into "Complete a task by voice"', 'Button "Add photo" <- eval/p2/strip-paracetamol.png', 'Button "Confirm"'],
    expect: ["Paracetamol 1 g given to bed 4.", HEARD, "Photo matches the task", "by voice"],
    before: ["Paracetamol 1 g given to bed 4.", HEARD],
    files: ["kumar-paracetamol.wav", "strip-paracetamol.png"],
    keyed: "1 Voice call and 1 Spark text call, plus 1 Spark vision call for the strip photo. Labels read Muse Voice and Muse Spark; Heard by reads Muse Voice. No switch.",
  },
  {
    id: "kumar-mycare", path: "kumar", role: "patient", seconds: 7, film: true,
    say: "Mr. Kumar's My care page shows the task as done by voice, with the photo check.",
    clicks: ["Role Patient", "Pick R. Kumar", 'Tab "My care"'],
    expect: [", by voice", "Photo matches the task"],
    keyed: "No model call.",
  },
  {
    id: "kumar-discharge", path: "kumar", role: "doctor", seconds: 8, film: true,
    say: "Dr. Rao adds a reference wound photo, dictates the discharge summary, and signs it.",
    clicks: ["Role Doctor", "Chart R. Kumar", 'Button "Add reference photo" <- eval/p4/wound-day0.png', 'File eval/p2/kumar-discharge.wav into "Dictate discharge"', 'Button "Sign discharge"'],
    expect: ["Reference", "15 of 15", HEARD, "Being discharged"],
    before: ["15 of 15"],
    files: ["wound-day0.png", "kumar-discharge.wav"],
    keyed: "1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark; Heard by reads Muse Voice. Live speech can be replaced by Or type what was said.",
  },
  {
    id: "kumar-home", path: "kumar", role: "nurse", seconds: 3, film: true,
    say: "The nurse completes the discharge checks and he goes home.",
    clicks: ["Role Nurse", DISCHARGE_BOXES, 'Button "Complete discharge"'],
    expect: ["Home"],
    keyed: "No model call.",
  },
  {
    id: "kumar-ask", path: "kumar", role: "patient", seconds: 12, film: true,
    say: "At home Mr. Kumar asks Dr. Rao about his wound and sends a day 3 photo; the page says who is waiting.",
    clicks: ["Role Patient", "Pick R. Kumar", "Tab Ask", 'Textarea in "Ask the doctor" <- Is the swelling normal on day 3?', 'Button "Send to Dr. Rao"', 'Text input in "Healing photo" <- Day 3', 'File input in "Healing photo" <- eval/p4/wound-day3.png'],
    expect: ["Waiting for Dr. Rao", "The doctor reviews the healing photo."],
    files: ["wound-day3.png"],
    keyed: "No model call.",
  },
  {
    id: "kumar-review", path: "kumar", role: "doctor", seconds: 9, film: true,
    say: "Dr. Rao opens the healing photo beside the reference photo and answers by voice.",
    clicks: ["Role Doctor", 'Tab "My queue"', 'Link "Open →" in the row with "Healing photo to review"', 'In "Ask inbox", the item with the question: file eval/p2/rao-answer.wav into "Answer by voice"', 'Button "Send answer"', 'Button "No visit needed"'],
    expect: ["Healing photo", "Reference", "by voice · Prepared demo result", "No visit needed"],
    before: [HEARD],
    files: ["rao-answer.wav"],
    keyed: "1 Voice call (hear). Heard by reads Muse Voice. No switch.",
  },
  {
    id: "kumar-answers", path: "kumar", role: "patient", seconds: 6, film: true,
    say: "Mr. Kumar sees the doctor's answer and the decision on his Ask page.",
    clicks: ["Role Patient", "Pick R. Kumar", "Tab Ask"],
    expect: ["The wound looks as expected for day 3.", "No visit needed"],
    keyed: "No model call.",
  },
  {
    id: "iyer-bp", path: "iyer", role: "nurse", seconds: 6, film: true,
    say: "Nurse Meena records Ms. Iyer's blood pressure by voice; it falls under the doctor's limit and is flagged.",
    clicks: ["Role Nurse", "Chart S. Iyer", 'File eval/p2/iyer-bp.wav into "Complete a task by voice"', 'Button "Confirm"'],
    expect: ["BP 82 over 54, pulse 112, bed 7.", "is below the limit of 90"],
    before: ["BP 82 over 54, pulse 112, bed 7."],
    files: ["iyer-bp.wav"],
    keyed: "1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark. No switch.",
  },
  {
    id: "iyer-orders", path: "iyer", role: "doctor", seconds: 7, film: true,
    say: "Dr. Rao sees the flagged reading in her queue, dictates saline orders, and signs them.",
    clicks: ["Role Doctor", 'Tab "My queue" (row shows "is below the limit of 90")', "Chart S. Iyer", 'File eval/p2/iyer-saline.wav into "Dictate orders"', 'Button "Sign orders"'],
    expect: ["Draft from dictation", "Nurse acknowledges the new orders from Dr. A. Rao (synthetic)."],
    files: ["iyer-saline.wav"],
    keyed: "1 Voice call and 1 Spark text call. Labels read Muse Voice and Muse Spark. Live speech can be replaced by Or type what was said.",
  },
  {
    id: "iyer-setup", path: "iyer", role: "nurse", seconds: 8, film: true,
    say: "The nurse acknowledges the orders, films the saline set-up, and the check matches the list before she begins.",
    clicks: ["Role Nurse", 'Button "Acknowledge"', 'File eval/p3/saline-setup.mp4 into the input labelled "Add video or photo check"', 'Button "Begin"'],
    expect: ["Set-up matches the list", `${SALINE} running`],
    files: ["saline-setup.mp4"],
    keyed: "SAM 3.1 video call. The label reads SAM 3.1. Switch: SETUP_LIVE.",
  },
  {
    id: "iyer-end", path: "iyer", role: "nurse", seconds: 2, film: true,
    say: "The clock moves two hours and the nurse ends the saline task.",
    clicks: ['Button "+1 h" twice', 'Button "End"'],
    expect: [`${SALINE} done`],
    keyed: "No model call.",
  },
  {
    id: "iyer-recheck", path: "iyer", role: "nurse", seconds: 5, film: true,
    say: "Her next reading is typed in and is back above the limit; the nurse answers the flag and it clears.",
    clicks: ["Role Nurse", 'Textarea in "Complete a task by voice" <- BP 112 over 70, pulse 84, bed 7.', 'Button "Use this text"', 'Radio "BP and pulse every 1 h"', 'Button "Confirm"', 'Field "What you did or saw" in the below-the-limit flag <- Reading checked again at the bedside', 'Button "Answer" in that flag'],
    expect: ["logged BP 112/70, HR 84"],
    absent: "→ Systolic BP 82 is below the limit of 90",
    keyed: "1 Spark text call (typed text, no Voice call). The label reads Muse Spark. No switch.",
  },
  {
    id: "iyer-discharge", path: "iyer", role: "doctor", seconds: 3, film: true,
    say: "Dr. Rao types a short summary and signs the discharge.",
    clicks: ["Role Doctor", 'Field "Summary" <- Recovered on the ward after saline. BP back above the limit.', 'Button "Sign discharge"'],
    expect: ["Being discharged"],
    keyed: "No model call.",
  },
  {
    id: "iyer-home", path: "iyer", role: "nurse", seconds: 2, film: true,
    say: "The discharge checks are ticked and she goes home.",
    clicks: ["Role Nurse", DISCHARGE_BOXES, 'Button "Complete discharge"'],
    expect: ["Home"],
    keyed: "No model call.",
  },
  {
    id: "iyer-meds", path: "iyer", role: "patient", seconds: 10, film: true,
    say: "Ms. Iyer photographs her medicines; the page flags one row and names each medicine with its schedule.",
    clicks: ["Role Patient", "Pick S. Iyer", "Tab Ask", 'File input in "Medicine photo" <- eval/p4/meds-iyer.png'],
    expect: ["Ibuprofen", "Pantoprazole 40 mg:"],
    files: ["meds-iyer.png"],
    keyed: "1 Spark vision call. The label reads Muse Spark. Switch: MEDICINES_LIVE.",
  },
  {
    id: "close", path: "close", role: "none", seconds: 3, film: true,
    say: "Back in the doctor's queue, Dr. Rao shows as available and every step above has a record.",
    clicks: ["Role Doctor", 'Tab "My queue"'],
    expect: ["Dr. A. Rao: Available"],
    keyed: "No model call.",
  },
];

export function roleSeconds(beats) {
  const sums = { doctor: 0, nurse: 0, patient: 0, none: 0 };
  for (const b of beats) if (b.film) sums[b.role] += b.seconds;
  return sums;
}

export function filmSeconds(beats) {
  return beats.filter((b) => b.film).reduce((total, b) => total + b.seconds, 0);
}

export function missingMedia(root, exists) {
  for (const [file, folder] of Object.entries(MEDIA)) {
    if (!exists(`${root}/${folder}/${file}`)) {
      return `Missing ${folder}/${file}. Run: .venv/bin/python ${GENERATOR[folder]} (or make demo-check).`;
    }
  }
  return "";
}

// The one beat table behind the two-app demo run (spec §11 A8, §12): one synthetic patient from Doctor Dictation
// through the Count Guard ward, theatre and discharge. Strings were checked against both apps on 2 Nov 2026.
export const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
export const ROLES = ["doctor", "nurse", "patient"];
export const APPS = ["dd", "cg"];
export const SCENES = ["title", "dd", "ward", "theatre", "discharge", "close"];
// Spec §12: 0:10–0:40 DD, 0:40–1:05 ward, 1:05–2:05 theatre, 2:05–2:45 discharge.
export const SCENE_SECONDS = { dd: 30, ward: 25, theatre: 60, discharge: 40 };

export const BANNER = "Research demo · Synthetic data · Not for clinical use";
export const PATIENT = "M. Fernandes, 52 F";

const MAKE_MEDIA = "eval/make_media.py";
export const MEDIA = {
  "wristband-synthetic.png": "eval/media/wristband",
  "wrong-photo-bed-rail-synthetic.png": "eval/media/wrong-photo",
  "consent-form.png": "eval/media/consent",
  "drug-lignocaine.wav": "eval/media/drug-phrases",
  "discharge-card.png": "eval/media/discharge",
  "medicine-bag-synthetic.png": "eval/media/medicine-bag",
};
export const GENERATOR = Object.fromEntries(Object.values(MEDIA).map((folder) => [folder, MAKE_MEDIA]));

const ADMISSION_BOXES = 'tick "Wristband on", "Allergies checked", "Baseline observations taken", "Consent on file"';
const DISCHARGE_BOXES = 'tick "Discharge card given", "Medicines handed over", "Reminders set"';
const MISSING = "One lap sponge was not seen back. It was last seen on the sterile field.";

export const BEATS = [
  {
    id: "title", scene: "title", app: "cg", role: "none", seconds: 10, film: true,
    say: "One synthetic patient, two apps: Doctor Dictation in the clinic and Count Guard on the ward, running with no live model.",
    clicks: ["Open http://127.0.0.1:8300/ (Doctor Dictation)", "Open http://127.0.0.1:5273/ (Count Guard)", "Role Doctor"],
    expect: [BANNER, "models: offline (prepared)"],
    keyed: "No model call. The dock reads models: live when a key is set.",
  },
  {
    id: "dd-open", scene: "dd", app: "dd", role: "doctor", seconds: 6, film: true,
    say: "Dr. Rao opens Doctor Dictation for a new clinic visit.",
    clicks: ["Switch to the Doctor Dictation tab"],
    expect: [BANNER, "Tap to dictate"],
    keyed: "No model call.",
  },
  {
    id: "dd-dictate", scene: "dd", app: "dd", role: "doctor", seconds: 14, film: true,
    say: "She dictates the visit; the prescription fills itself and every medicine is checked.",
    clicks: ['Button "Tap to dictate"', "Speak about 3 s", 'Button "Tap to dictate" again to finish'],
    expect: ["M. Fernandes (synthetic)", "52 F", "Paracetamol", "All medicines are ready. You can Save."],
    keyed: "1 Muse Voice Transcribe call and 1 Spark text call for the structured prescription (DD: STT_ENGINE=muse, LLM_PROVIDER=meta).",
  },
  {
    id: "dd-admit", scene: "dd", app: "dd", role: "doctor", seconds: 10, film: true,
    say: "She types the reason and saves with Save & admit to ward; the page says when Count Guard has the patient.",
    clicks: ['Button "Save & admit to ward"', 'Field "Reason for admission" <- Right inguinal hernia repair', 'Button "Save & admit to ward"'],
    expect: ["Saved and in Count Guard."],
    // The first status after the save; "Sending" lasts about 1 s, so either line counts.
    firstOf: ["Saved. Sending to Count Guard…", "Saved and in Count Guard."],
    keyed: "No model call. The push goes to Count Guard's intake with the shared token.",
  },
  {
    id: "ward-arrival", scene: "ward", app: "cg", role: "nurse", seconds: 7, film: true, arrivalMs: 3000,
    say: "On the Count Guard ward, Nurse Meena sees Ms. Fernandes arrive, being admitted, with the clinic prescription.",
    clicks: ["Switch to the Count Guard tab", "Role Nurse", 'Tab "Patients"'],
    expect: [BANNER, PATIENT, "Being admitted"],
    keyed: "No model call.",
  },
  {
    id: "ward-photo-ok", scene: "ward", app: "cg", role: "nurse", seconds: 6, film: true,
    say: "She photographs the wristband; the photo check accepts it and says what it saw.",
    clicks: [`Chart ${PATIENT}`, 'File eval/media/wristband/wristband-synthetic.png into "Photo check: Wristband on"'],
    expect: ["Photo matches — The photo shows a patient wristband with the patient's name printed on it. · Prepared", "Doctor Dictation PDF"],
    files: ["wristband-synthetic.png"],
    keyed: "1 Spark vision call. The verdict reads without · Prepared. Switch: PROOF_LIVE.",
  },
  {
    id: "ward-photo-wrong", scene: "ward", app: "cg", role: "nurse", seconds: 6, film: true,
    say: "A photo of the bed rail is sent for the consent form; the check does not accept it, and the item stays open.",
    clicks: ['File eval/media/wrong-photo/wrong-photo-bed-rail-synthetic.png into "Photo check: Consent on file"'],
    expect: ["Photo does not match — The photo shows a bed rail, not a signed consent form. · Prepared", "Reason to override"],
    files: ["wrong-photo-bed-rail-synthetic.png"],
    keyed: "1 Spark vision call. Switch: PROOF_LIVE. With the model unavailable the line reads Not checked — model unavailable.",
  },
  {
    id: "ward-retake", scene: "ward", app: "cg", role: "nurse", seconds: 6, film: true,
    say: "She takes the photo again with the signed form, ticks the checklist and completes the admission.",
    clicks: ['Button "Take the photo again" in "Photo check: Consent on file" <- eval/media/consent/consent-form.png', ADMISSION_BOXES, 'Button "Complete admission"'],
    expect: ["On the ward"],
    before: ["Photo matches — The photo shows a signed consent form"],
    files: ["consent-form.png"],
    keyed: "1 Spark vision call. Switch: PROOF_LIVE.",
  },
  {
    id: "theatre-send", scene: "theatre", app: "cg", role: "doctor", seconds: 6, film: true,
    say: "Dr. Rao picks the hernia repair and sends her to theatre.",
    clicks: ["Role Doctor", 'Select "Procedure" <- hernia-repair', 'Button "Send to theatre"'],
    expect: ["In theatre"],
    keyed: "No model call.",
  },
  {
    id: "theatre-drug", scene: "theatre", app: "cg", role: "nurse", seconds: 10, film: true,
    say: "In theatre the local anaesthetic is said aloud; the heard line is drafted, and the nurse confirms it was given.",
    clicks: ["Role Nurse", 'File eval/media/drug-phrases/drug-lignocaine.wav into "Upload audio" in "Drug given"', 'Button "Add heard line"', 'Button "Confirm given"'],
    expect: ["lignocaine 2% 5 ml local infiltration", "From voice", "Accepted by Nurse Asha"],
    before: ["Heard, not confirmed"],
    files: ["drug-lignocaine.wav"],
    keyed: "1 Muse Voice Transcribe call. The row reads From voice without · Prepared. Switch: VOICE_LIVE.",
  },
  {
    id: "theatre-card", scene: "theatre", app: "cg", role: "nurse", seconds: 10, film: true,
    say: "The simulated vitals strip plays; the blood pressure falls, and the context card sets the numbers side by side.",
    clicks: ['Button "Next reading" four times', 'Tick "Context card (research tier)"'],
    expect: ["BP 86/50 · HR 76 · Simulated", "Research demo — not for clinical use", "BP 86/50, down 28% in 4 min. HR not rising.", "Template from the record"],
    keyed: "1 Spark text call words the card, with the wording check; the source reads Worded by AI from the record. Switch: SPARK_LIVE.",
  },
  {
    id: "theatre-camera", scene: "theatre", app: "cg", role: "nurse", seconds: 10, film: true,
    say: "Surgery begins, the pack is recorded, and the swab camera watches the recorded theatre clip.",
    clicks: ['Button "Surgery began"', 'Button "Record pack opened" (prefilled 15)', 'Button "Start the swab camera"', 'Button "Play the recorded theatre clip"'],
    expect: ["Advice only. The count a person saves decides.", "Read by camera", "The camera saw 9 of 10 lap sponges back at the closing count."],
    keyed: "SAM 3.1 video call on the clip (make cost CLIP=<file> for the bill). Switch: SWABS_LIVE.",
  },
  {
    id: "theatre-missing", scene: "theatre", app: "cg", role: "nurse", seconds: 10, film: true,
    say: "One sponge was not seen back, and the camera shows the last frame it was seen in.",
    clicks: ['Scroll to the advice "One lap sponge was not seen back"', "Image: Last frame the camera saw it in"],
    expect: [MISSING],
    keyed: "No further call: the frame comes from the same video call.",
  },
  {
    id: "theatre-hard-stop", scene: "theatre", app: "cg", role: "nurse", seconds: 8, film: true,
    say: "The nurse types 14 back of 15; the reason is required, and surgery cannot end until a person saves the count.",
    clicks: ['Field "Closing count (returned)" <- 14'],
    expect: ["What did the team do? (required)", "Surgery ended unlocks when the count is saved."],
    keyed: "No model call. The step also posts surgery ended to the API and expects 409 (the count gate).",
  },
  {
    id: "theatre-reconcile", scene: "theatre", app: "cg", role: "nurse", seconds: 6, film: true,
    say: "The sponge is found under the drape; she notes it on the advice, saves 15 of 15, and surgery ends.",
    clicks: ['Field "If you disagree, say why" on the missing sponge <- Found under the drape, counted by hand', 'Button "Acknowledge"', 'Field "Closing count (returned)" <- 15', 'Button "Save count as Nurse Asha"', 'Button "Surgery ended"', 'Button "Back to ward"'],
    expect: ["Ward · back from theatre"],
    before: ["Found under the drape, counted by hand", "Count complete"],
    keyed: "No model call.",
  },
  {
    id: "discharge-draft", scene: "discharge", app: "cg", role: "doctor", seconds: 14, film: true,
    say: "Dr. Rao presses Draft discharge; the draft fills itself from the record: the prescription, the drug given and the count.",
    clicks: ["Role Doctor", 'Button "Draft discharge"'],
    expect: ["Drafted from the record", "Paracetamol 500 mg 1-1-1", "lignocaine 2% 5 ml local infiltration · by Nurse Asha", "opened 15 / returned 15, 0 unaccounted · saved by Nurse Asha"],
    keyed: "1 Spark text call words the summary (template text if it fails). Switch: SPARK_LIVE.",
  },
  {
    id: "discharge-sign", scene: "discharge", app: "cg", role: "doctor", seconds: 6, film: true,
    say: "She checks the summary and signs the discharge.",
    clicks: ['Button "Sign discharge"'],
    expect: ["Being discharged"],
    before: ["Discharge PDF", "Follow-up in calendar"],
    keyed: "No model call.",
  },
  {
    id: "discharge-pdf", scene: "discharge", app: "cg", role: "doctor", seconds: 8, film: true,
    say: "The signed discharge PDF opens with the drug log and the count, and the follow-up goes to the calendar.",
    clicks: ["Open /journey/episodes/<id>/discharge.pdf (the Discharge PDF link)", "Open /journey/episodes/<id>/follow-up.ics"],
    expect: ["Being discharged"],
    pdf: ["Research demo", "lignocaine 2% 5 ml local infiltration", "Opened 15. Returned 15. Unaccounted 0."],
    keyed: "No model call. The step reads the PDF's text and checks the drug and the count are in it.",
  },
  {
    id: "discharge-home", scene: "discharge", app: "cg", role: "nurse", seconds: 12, film: true,
    say: "The nurse photographs the discharge card and the medicine bag, ticks the checks, and Ms. Fernandes goes home.",
    clicks: ["Role Nurse", 'File eval/media/discharge/discharge-card.png into "Photo check: Discharge card given"', 'File eval/media/medicine-bag/medicine-bag-synthetic.png into "Photo check: Medicines handed over"', DISCHARGE_BOXES, 'Button "Complete discharge"'],
    expect: ["Home"],
    before: ["shows the discharge card", "shows a medicine bag"],
    files: ["discharge-card.png", "medicine-bag-synthetic.png"],
    keyed: "2 Spark vision calls. Switch: PROOF_LIVE.",
  },
  {
    id: "close", scene: "close", app: "cg", role: "doctor", seconds: 15, film: true,
    say: "Back on My patients, every step has a record. The system formats. The doctor decides.",
    clicks: ['Tab "My patients"'],
    expect: [BANNER, "Available"],
    keyed: "No model call.",
  },
];

export function sceneSeconds(beats) {
  const sums = Object.fromEntries(SCENES.map((s) => [s, 0]));
  for (const b of beats) if (b.film) sums[b.scene] += b.seconds;
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

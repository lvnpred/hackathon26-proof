// The Help page copy (spec 9, from the old morning guide). Plain words only: no event names, no model names.
// Each section says where to do it and what it does. Nothing here tells anyone what to do medically.
const SECTIONS = [
  { id: "medicines", title: "Medicines from home", who: "Doctor", where: "A patient's chart, before the operation",
    does: "Photograph the strips the patient brought, or type one medicine per line. Each one is matched to the prescription. A medicine name the list does not know stays as read; it is not guessed." },
  { id: "pack", title: "Say what was opened", who: "Nurse", where: "A patient in theatre",
    does: "Say or type a line such as \"opening twenty swabs\". That sets the number to count back." },
  { id: "count", title: "Count what came back", who: "Nurse", where: "A patient in theatre",
    does: "Add a swab by hand or run the camera. A swab counts as back only after it stays in the bucket. The count a person saves decides; the camera only advises." },
  { id: "drugs", title: "Record what was given", who: "Nurse and doctor", where: "A patient in theatre",
    does: "Hear a drug line, then confirm it. Nothing is on the sheet until a person confirms." },
  { id: "pressure", title: "Record the blood pressure", who: "Nurse", where: "A patient in theatre or ward",
    does: "Log each reading. The numbers are a record, not a plan. The fact card stays off unless you turn it on." },
  { id: "sheet", title: "Write the discharge sheet", who: "Doctor", where: "A patient after the operation",
    does: "The sheet lists only what was recorded. It does not say what to do next medically." },
  { id: "evidence", title: "See what the camera saw", who: "Doctor and nurse", where: "Inspect any result, then Evidence",
    does: "Open the kept frames, the tracked items and the camera's notes for this patient's theatre stay." },
];

export const PATIENT_RULE =
  "These steps are for one patient at a time. The next patient starts a new record. Records are not mixed.";

// One line per role, with the care screen they start on.
export const AUDIENCES = [
  { who: "Doctor", does: "Open a patient's chart, write the prescription, photograph or type the medicines from home, and sign the discharge sheet.", start: "/patients" },
  { who: "Nurse", does: "Work the queue: counts, drug lines, blood pressure and handover for each patient.", start: "/queue" },
  { who: "Patient", does: "See today's plan, your care so far, and ask a question about it.", start: "/today" },
];

export const helpSections = () => SECTIONS;

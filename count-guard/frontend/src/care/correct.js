// Correct a recorded line (spec §9): Inspector → History, and the theatre drug row. Pure helpers for node --test.
// The server decides what may be corrected (journey/correction.py); the button shows only where it would say yes.
const DOCTOR = "Dr. A. Rao (synthetic)"; // as in DoctorActions.jsx (JSX, so node --test cannot import it)
const WARD_NURSE = "Nurse Meena (synthetic)"; // the ward nurse, as in NurseActions.jsx

// [key, label, kind, options]. kind: "int" (a whole number), "number", "text" or "choice".
const OBS = [
  ["sbp", "Systolic BP", "int"],
  ["dbp", "Diastolic BP", "int"],
  ["hr", "Heart rate", "int"],
  ["spo2", "SpO2", "int"],
  ["temp", "Temperature", "number"],
];
// A drug line's dose and route only: never the name, who gave it, or which heard line it confirms.
const DRUG = [
  ["strength", "Strength", "text"],
  ["amount", "Amount", "number"],
  ["unit", "Unit", "choice", ["mcg", "mg", "g", "ml"]],
  ["route", "Route", "choice", ["local infiltration", "iv", "im", "subcutaneous", "oral"]],
];
const FIELDS = { "obs.recorded": OBS, "drug.given": DRUG, "druglog.given": DRUG, "druglog.parsed": DRUG };

export const fieldsFor = (type) => FIELDS[type] || [];

export const canCorrect = (written) => Boolean(written) && Object.hasOwn(FIELDS, written.type);

export const correctorFor = (role) => (role === "doctor" ? DOCTOR : WARD_NURSE);

function value(text, label, kind) {
  if (kind === "text" || kind === "choice") return { value: text };
  const n = Number(text);
  if (kind === "int" && !Number.isInteger(n)) return { error: `${label} must be a whole number.` };
  if (!Number.isFinite(n)) return { error: `${label} must be a number.` };
  if (kind === "number" && label === "Amount" && n <= 0) return { error: "Amount must be more than 0." };
  return { value: n };
}

// { body } for POST /correct, or { error } in staff words. Blank fields keep their recorded value.
export function correctionBody(written, form, by) {
  const payload = {};
  for (const [key, label, kind] of fieldsFor(written.type)) {
    const text = String(form?.[key] ?? "").trim();
    if (!text) continue;
    const got = value(text, label, kind);
    if (got.error) return { error: got.error };
    payload[key] = got.value;
  }
  if (!Object.keys(payload).length) return { error: "Type the value to correct." };
  return { body: { event_id: written.event_id, payload, by } };
}

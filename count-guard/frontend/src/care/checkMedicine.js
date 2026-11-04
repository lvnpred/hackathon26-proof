// The patient's own words for one checked medicine (Task 8), as pure parts so node --test reads them.
// checkMatchLine(kind) maps the backend match kind; an unknown kind fails safe to the doctor.
// CHECK_COPY lists every fixed line of the card; the test sweeps all but ALLOW for advice words.
export const CHECK_MATCH = {
  on_prescription: "On your prescription",
  strength_differs: "Strength differs from your prescription",
  not_on_prescription: "Not on your prescription — ask your doctor",
  no_prescription: "No prescription yet.",
};

export const checkMatchLine = (kind) => CHECK_MATCH[kind] || CHECK_MATCH.not_on_prescription;

// The one fixed line allowed past the advice-word sweep (it names the doctor, not an instruction).
export const ALLOW = ["Not on your prescription — ask your doctor"];

export const CHECK_COPY = [
  "Check a medicine",
  "A photo of one strip, or its typed name. Each is matched to your prescription.",
  "Add a photo",
  "Type instead",
  "Name",
  "Strength (optional)",
  "Check this medicine",
  ...Object.values(CHECK_MATCH),
];

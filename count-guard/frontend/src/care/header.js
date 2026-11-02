// The chart header's facts about the patient, from the server's `header` (bed, age/sex, OP number,
// diagnosis, the Doctor Dictation doctor and PDF link). Empty facts are left out.
export function headerFacts(header) {
  if (!header) return [];
  const facts = [
    ["Age/sex", header.age_sex],
    ["OP number", header.op_no],
    ["Diagnosis", (header.diagnosis || []).join("; ")],
    ["Doctor in Doctor Dictation", header.dd_doctor],
  ];
  return facts.filter(([, value]) => value).map(([label, value]) => ({ label, value }));
}

// A plain reason the bed cannot be sent, or "" when it can. The server still refuses a taken bed.
export function bedProblem(bed, current) {
  const text = (bed || "").trim();
  if (!text) return "Type a bed number.";
  if (!/^[A-Za-z0-9-]{1,8}$/.test(text)) return "Use letters, numbers or a dash.";
  if (text === current) return `The patient is already in bed ${current}.`;
  return "";
}

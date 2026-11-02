// Pure helpers for the ward list's Sync and New patient buttons.

export const syncSummary = ({ new: added, existing, updated, failed }) =>
  `${added} new, ${existing} already here, ${updated} updated${failed ? `, ${failed} could not be read` : ""}`;

// "" when the form can be sent. While the demo is on, every name carries the synthetic tag.
export function newPatientError({ name }) {
  const text = String(name || "").trim();
  if (!text) return "Enter a name";
  return text.endsWith("(synthetic)") ? "" : 'Add "(synthetic)" to the name';
}

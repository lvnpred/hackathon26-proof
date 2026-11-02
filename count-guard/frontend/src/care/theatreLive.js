// The three theatre panels (spec §6.4): drug given by voice, the simulated vitals strip, the context card.
// Plain staff words only: no event names, no model names.
import { hhmm } from "./clock.js";
import { displayName } from "./names.js";

export const RESEARCH_BANNER = "Research demo — not for clinical use";
export const SIMULATED = "Simulated";

// One reading of the strip: "BP 86/50 · HR 76 · Simulated". Every reading here is simulated (spec §6.4).
export function vitalsLabel(reading) {
  return `BP ${reading.systolic}/${reading.diastolic} · HR ${reading.hr} · ${SIMULATED}`;
}

// "lignocaine 2% 5 ml local infiltration" from a heard row.
export function drugLine(row) {
  const name = row.generic || row.name_as_heard || "Unknown medicine";
  return [name, row.strength, row.amount != null ? `${row.amount} ${row.unit || ""}`.trim() : null, row.route].filter(Boolean).join(" ");
}

// Under a heard row: what a person still has to do, or who confirmed it.
export function drugStatus(row) {
  if (row.given) return `Given ${hhmm(row.given.at_ms)} · confirmed by ${displayName(row.given.by)}`;
  if (!row.grounded) return "Not in the drug list. Check the name before confirming.";
  return "Heard, not confirmed";
}

export function heardPackLine(pack) {
  const status = pack.confirmed_by ? `pack confirmed by ${displayName(pack.confirmed_by)}` : "not counted until a person confirms";
  return `Heard “${pack.text}” · ${pack.n} ${pack.item_type}${pack.n === 1 ? "" : "s"} · ${status}`;
}

// The card's source words: Spark-worded text, or the template from the record. Never a model name.
export function cardWords(card) {
  return card?.wording === "llm" ? "Worded by AI from the record" : "Template from the record";
}

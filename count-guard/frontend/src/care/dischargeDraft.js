// The discharge draft written from the timeline (spec §6.8), in staff words. Pure, so node --test can read it.
export const FROM_TIMELINE = "Drafted from the record";

const joined = (parts) => parts.filter((p) => p !== "" && p !== null && p !== undefined).join(" ");

// The summary box's first text: the timeline summary, then any dictated sections under it.
export function draftSummary(draft) {
  if (!draft) return "";
  const dictated = (draft.sections || []).map((s) => `${s.heading}: ${s.text}`).join("\n");
  return [draft.summary, dictated].filter(Boolean).join("\n\n");
}

// The five sections the doctor checks: [{ title, lines }]. A section with nothing recorded says so.
export function draftSections(timeline) {
  if (!timeline) return [];
  const rx = timeline.prescription;
  const none = (lines, empty) => (lines.length ? lines : [empty]);
  return [
    { title: "Prescription", lines: none((rx?.rows || []).map((r) => joined([r.name, r.strength, r.dose, r.instructions && `· ${r.instructions}`])), "No prescription recorded.") },
    { title: "Drugs given", lines: none((timeline.drugs_given || []).map((d) => `${joined([d.name, d.strength, d.amount, d.unit, d.route])} · by ${d.by}, ${d.when}`), "No drug given in theatre.") },
    { title: "Swab count", lines: [timeline.count ? `${timeline.count.text} · saved by ${timeline.count.by}` : "No count saved by a person."] },
    { title: "Key events", lines: none((timeline.events || []).map((m) => `${m.when}: ${m.text}`), "No moves recorded.") },
    { title: "Follow-up", lines: [timeline.follow_up ? `${timeline.follow_up.text}, ${timeline.follow_up.when}` : "None."] },
  ];
}

// The PDF and the follow-up calendar file of this episode.
export const dischargeLinks = (episodeId) => ({
  pdf: `/journey/episodes/${episodeId}/discharge.pdf`,
  ics: `/journey/episodes/${episodeId}/follow-up.ics`,
});

// Dictated sentences no section rule placed (clarity §4.5): the doctor chooses a section; nothing goes to "Course".
export const NOT_PLACED = "Not placed — choose a section";
export const SECTION_HEADINGS = ["Diagnosis", "Procedure", "Course on the ward", "Medicines", "Follow-up"];
export const LEAVE_OUT = "Leave out";

// settled: { index in draft.unplaced: a heading, or LEAVE_OUT }. Keyed by index, so a sentence said twice is two choices.
// The sentences still waiting ([{ index, text }]) and the ones left out (texts, each as often as it was left out).
export const pendingUnplaced = (unplaced, settled) => (unplaced || []).map((text, index) => ({ index, text })).filter(({ index }) => !(settled || {})[index]);
export const leftOutOf = (unplaced, settled) => (unplaced || []).filter((_, index) => (settled || {})[index] === LEAVE_OUT);
export const notPlacedLine = (n) => `${n} sentence${n === 1 ? "" : "s"} not placed`;

// The summary with `sentence` added under `heading`: to that heading's line when there is one, else as a new line.
export function placeSentence(summary, heading, sentence) {
  const lines = summary ? summary.split("\n") : [];
  const at = lines.findIndex((line) => line.startsWith(`${heading}:`));
  if (at >= 0) lines[at] = `${lines[at].trimEnd()} ${sentence}`;
  else lines.push(`${heading}: ${sentence}`);
  return lines.join("\n");
}

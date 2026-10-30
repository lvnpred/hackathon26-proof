// Which timeline types each lens keeps. "everyone" has no entry: the chart shows the audit rows instead.
export const LENSES = {
  nurse: ["count.", "dose.", "obs.", "handover.", "nudge.", "patient.state", "order.", "task.", "surgery.", "discharge."],
  doctor: ["rx.", "ward.orders", "discharge.", "druglog.", "patient.state", "order.", "task.", "surgery."],
  patient: ["brownbag.", "reminders.", "checkin.", "help.", "patient.state", "order.signed", "task.done", "surgery.", "discharge."],
};

// One line per event in time order. Open alerts are answered in the chart banner, never here.
// A line a lens filters out still shows when the nudge is for the current role or is the deep-linked line.
export default function Timeline({ lines, nudges, replaced, lens, role, line }) {
  const open = Object.fromEntries(nudges.map((nudge) => [nudge.id, nudge]));
  const prefixes = LENSES[lens] || [];
  const shown = lines.filter((item) => {
    if (lens === "patient" && item.patient === "") return false; // staff-only wording
    const nudge = open[item.id];
    if (nudge && (nudge.to === role || nudge.id === line)) return true;
    return prefixes.some((prefix) => item.type.startsWith(prefix));
  });
  if (!shown.length) return <p className="empty small">Nothing recorded for this lens yet.</p>;
  return (
    <ol className="timeline" aria-label="Timeline">
      {shown.map((item) => {
        const hit = item.id === line ? " line-hit" : "";
        const struck = replaced.has(item.id);
        return (
          <li key={item.id} id={item.id} data-line={item.id} className={`${struck ? "struck" : ""}${hit}`.trim() || undefined}>
            <span className="tag">{item.when}</span> <span>{lens === "patient" ? item.patient ?? item.plain : item.plain}</span>
            {struck && <> <span className="tag">corrected</span></>}
          </li>
        );
      })}
    </ol>
  );
}

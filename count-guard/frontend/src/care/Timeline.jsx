import { Nudge } from "../screens/WardPanel";

// Which timeline types each lens keeps. "everyone" has no entry: the chart shows the audit rows instead.
export const LENSES = {
  nurse: ["count.", "dose.", "obs.", "handover.", "nudge."],
  doctor: ["rx.", "ward.orders", "discharge.card", "druglog."],
  patient: ["brownbag.", "reminders.", "checkin.", "help."],
};

// One line per event in time order. An open nudge replaces its own "nudge.raised" line and keeps its actions.
// readOnly shows an open nudge as a plain line with no actions (My care).
// A line a lens filters out still shows when the nudge is for the current role or is the deep-linked line.
export default function Timeline({ lines, nudges, replaced, lens, role, line, busy, act, readOnly }) {
  const open = Object.fromEntries(nudges.map((nudge) => [nudge.id, nudge]));
  const prefixes = LENSES[lens] || [];
  const shown = lines.filter((item) => {
    const nudge = open[item.id];
    if (nudge && (nudge.to === role || nudge.id === line)) return true;
    return prefixes.some((prefix) => item.type.startsWith(prefix));
  });
  if (!shown.length) return <p className="empty small">Nothing recorded for this lens yet.</p>;
  return (
    <ol className="timeline" aria-label="Timeline">
      {shown.map((item) => {
        const nudge = open[item.id];
        const hit = item.id === line ? " line-hit" : "";
        if (nudge && !readOnly) {
          return (
            <li key={item.id} id={item.id} data-line={item.id} className={`tl-nudge${hit}`}>
              <Nudge nudge={nudge} busy={busy} act={act} />
            </li>
          );
        }
        const struck = replaced.has(item.id);
        return (
          <li key={item.id} id={item.id} data-line={item.id} className={`${struck ? "struck" : ""}${hit}`.trim() || undefined}>
            <span className="tag">{item.when}</span> <span>{item.plain}</span>
            {struck && <> <span className="tag">corrected</span></>}
          </li>
        );
      })}
    </ol>
  );
}

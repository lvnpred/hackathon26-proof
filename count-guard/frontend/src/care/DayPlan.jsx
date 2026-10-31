import { askAboutText, cropStyle } from "./brownbag.js";
import { useInspector } from "./Inspector.jsx";

const EMPTY = "Your medicines appear here once the doctor's prescription is in.";

function Item({ item, bbox, photoUrl, onInspect }) {
  return (
    <li className="plan-item">
      {bbox && photoUrl && <span className="crop" style={cropStyle(bbox, photoUrl)} aria-hidden="true" />}
      <span><b>{item.medicine}</b><br /><span className="small">{item.text}</span></span>
      {onInspect && <button type="button" className="quiet" onClick={onInspect}>Inspect <span aria-hidden="true">›</span></button>}
    </li>
  );
}

// The day plan restates the prescription only: slots, as needed, and doses written in words (R25, R26).
export default function DayPlan({ plan, photoUrl, regions = [], onAsk, moment = null, episodeId }) {
  const { openInspector } = useInspector();
  const inspect = (row) => (moment ? () => openInspector(moment.id, { episodeId, focus: row.key }) : null);
  if (!plan) return <p className="empty small">{EMPTY}</p>;
  const rows = [["Morning", plan.slots.morning], ["Afternoon", plan.slots.afternoon], ["Night", plan.slots.night], ["As needed", plan.as_needed]];
  if (plan.as_written.length) rows.push(["As written", plan.as_written]);
  return (
    <div className="stack">
      <div className="plan-grid">
        {rows.map(([title, items]) => (
          <div className="plan-row" key={title}>
            <p className="label">{title}</p>
            {items.length ? <ul className="plan-list">{items.map((item, i) => <Item key={`${item.key}-${i}`} item={item} bbox={item.region == null ? null : regions[item.region]?.bbox} photoUrl={photoUrl} onInspect={inspect(item)} />)}</ul> : <p className="small muted">None</p>}
          </div>
        ))}
      </div>
      {plan.not_prescribed.length > 0 && (
        <div className="stack">
          <p className="note">Not on your prescription: {plan.not_prescribed.map((n) => n.name).join(", ")}</p>
          {plan.not_prescribed.map((n) => (
            <button key={n.read} onClick={() => onAsk(askAboutText(n.read))}>Ask Dr. Rao <span className="small muted">about {n.name}</span></button>
          ))}
        </div>
      )}
    </div>
  );
}

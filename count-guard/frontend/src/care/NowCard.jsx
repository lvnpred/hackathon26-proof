import { useState } from "react";
import Fold from "./Fold.jsx";
import StatusPill from "./StatusPill.jsx";

function Row({ item }) {
  return (
    <li className="now-row">
      <span>{item.patient ? `Bed ${item.patient.bed} · ${item.title}` : item.title}</span>
      <StatusPill role={item.pill.role} text={item.pill.text} />
    </li>
  );
}

// The one Now of a screen. `pick` comes from pickNow or pickNowAcross. The step's buttons (children) are the only
// primary buttons while the step is Now; when something else is Now they stay reachable but quiet.
export default function NowCard({ pick, card = null, lead = null, footer = null, children = null }) {
  const [open, setOpen] = useState(false);
  const { now, next, more, rest } = pick;
  const stepIsNow = now.action?.kind === "step";
  const eyebrow = now.rank === 6 && card ? card.eyebrow : "Now · for you";
  return (
    <section className="card now-card" aria-label="Now">
      <p className="label">{eyebrow}</p>
      <div className="row between">
        <h2 className="t-heading">{now.patient ? `Bed ${now.patient.bed}, ${now.patient.name} · ${now.title}` : now.title}</h2>
        <StatusPill role={now.pill.role} text={now.pill.text} />
      </div>
      {now.detail && <p className="now-detail">{now.detail}</p>}
      {lead}
      {children && <div className={stepIsNow ? "now-action" : "now-action now-quiet"}>{children}</div>}
      {next.length > 0 && (
        <div className="now-next">
          <p className="label">Next after this</p>
          <ul className="now-rows">{next.map((item, i) => <Row key={i} item={item} />)}</ul>
        </div>
      )}
      {rest > 0 && (
        <Fold label={`${rest} more`} open={open} onToggle={() => setOpen(!open)}>
          <ul className="now-rows">{more.map((item, i) => <Row key={i} item={item} />)}</ul>
        </Fold>
      )}
      {card && now.rank < 6 && !card.mine && <p className="small muted">Next: {card.text}</p>}
      {card && <p className="small muted">{card.last}</p>}
      {footer}
    </section>
  );
}

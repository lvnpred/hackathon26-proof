import { Link, NavLink } from "react-router-dom";
import { Mark } from "../App";
import { IconBell } from "./icons.jsx";
import { aiChip, alertsLabel, pauseLabel, pausedText } from "./dock";
import { SIGNED_IN, initials } from "./people";
import { atText } from "./when";

// Ward-wide, staff only. The Resume button is the same switch as the header's.
export function PausedBanner({ ops, nowMs }) {
  if (!ops.paused) return null;
  return (
    <div className="paused-banner" role="status">
      <span>{pausedText(ops.by, ops.atMs == null ? "" : atText(ops.atMs, nowMs))}</span>
      <button type="button" disabled={ops.busy} onClick={ops.toggle}>Resume</button>
    </div>
  );
}

// Brand, ward, main nav and (staff) alerts, AI admin switch and the signed-in person. On a phone: mark, bell, Pause, initials.
export default function ProductHeader({ role, tabs, unread, alerts, alertsOpen, onAlerts, ops }) {
  const staff = role !== "patient";
  const person = SIGNED_IN[role];
  return (
    <header className="app-bar">
      <Link to="/" className="brand">
        <span className="brand-logo"><Mark /></span>
        <span className="brand-names">
          <span className="brand-name"><b>Count Guard</b></span>
          {staff && <span className="brand-sub">Ward 4</span>}
        </span>
      </Link>
      <nav className="nav" aria-label="Main">
        {tabs.map(([to, name]) => (
          <NavLink key={to} to={to}>{name}{to === "/ask" && unread > 0 && <span className="dot" aria-hidden="true" />}</NavLink>
        ))}
      </nav>
      {staff && alerts > 0 && (
        <button type="button" className="pill wait bell" aria-expanded={alertsOpen} onClick={onAlerts}>
          <IconBell />
          <span className="bell-text">{alertsLabel(alerts)}</span>
          <span className="bell-count" aria-hidden="true">{alerts}</span>
        </button>
      )}
      {staff && ops.paused != null && (
        <span className="ai-admin">
          <span className="ai-admin-state">{aiChip(ops.paused)}</span>
          <button type="button" disabled={ops.busy} onClick={ops.toggle}>{pauseLabel(ops.paused)}</button>
          {ops.error && <span className="error small" role="alert">{ops.error}</span>}
        </span>
      )}
      {person && (
        <span className="signed-in">
          <span className="avatar" aria-hidden="true">{initials(person.name)}</span>
          <span className="signed-in-name">{person.name} · {person.role}</span>
        </span>
      )}
    </header>
  );
}

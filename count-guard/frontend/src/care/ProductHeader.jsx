import { Link, NavLink } from "react-router-dom";
import { Mark } from "../App";
import { alertsLabel } from "./dock";
import { SIGNED_IN, initials } from "./people";
import { whenText } from "./when";

export function pausedText(by, atMs, nowMs) {
  const at = atMs == null ? "" : ` at ${whenText(atMs, nowMs)}`;
  return `AI admin is paused for Ward 4. Paused by ${by || "a person"}${at}. New orders and tasks wait for a person.`;
}

// Ward-wide, staff only. The Resume button is the same switch as the header's.
export function PausedBanner({ ops, nowMs }) {
  if (!ops.paused) return null;
  return (
    <div className="paused-banner" role="status">
      <span>{pausedText(ops.by, ops.atMs, nowMs)}</span>
      <button type="button" disabled={ops.busy} onClick={ops.toggle}>Resume</button>
    </div>
  );
}

// Brand, ward, main nav and (staff) alerts, doctor status, AI admin switch and the signed-in person.
export default function ProductHeader({ role, tabs, unread, alerts, alertsOpen, onAlerts, ops, chip }) {
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
        <button type="button" className="pill wait" aria-expanded={alertsOpen} onClick={onAlerts}>
          {alertsLabel(alerts)}
        </button>
      )}
      {staff && chip}
      {staff && ops.paused != null && (
        <span className="ai-admin">
          <span>AI admin: {ops.paused ? "paused" : "on"}</span>
          <button type="button" disabled={ops.busy} onClick={ops.toggle}>{ops.paused ? "Resume" : "Pause"}</button>
          {ops.error && <span className="error small" role="alert">{ops.error}</span>}
        </span>
      )}
      {person && (
        <span className="signed-in">
          <span className="avatar" aria-hidden="true">{initials(person.name)}</span>
          <span>{person.name} · {person.role}</span>
        </span>
      )}
    </header>
  );
}

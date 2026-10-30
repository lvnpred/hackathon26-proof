import { useState } from "react";
import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { Nudge } from "../screens/WardPanel";
import { DEMO, useCareWard } from "./CareShell";
import Fault from "./Fault";
import { NUDGE_SCOPES, STATUS } from "./faults";
import { queueRows } from "./derive";
import { StateBadge } from "./Patients";
import { STATUS_CHOICES } from "./status";

function QueueRow({ row, ward, open, toggle }) {
  const patient = ward.find(row.episodeId);
  const nudge = (patient?.view.nudges || []).find((n) => n.id === row.lineId);
  const to = `/chart/${row.episodeId}${row.lineId ? `?line=${row.lineId}` : ""}`;
  return (
    <>
      <tr>
        <td className="num">Bed {row.bed}</td>
        <td className="left">{row.name}</td>
        <td>{row.says}</td>
        <td>{row.waited}</td>
        <td>
          {DEMO && nudge && <button onClick={toggle}>{open ? "Close" : "Answer"}</button>} <Link to={to}>Open →</Link>
        </td>
      </tr>
      {open && nudge && (
        <tr>
          <td colSpan={5}>
            <Nudge nudge={nudge} busy={ward.busy} act={(path, body) => ward.act(row.episodeId, path, body)} />
            <Fault fault={ward.fault} episodeId={row.episodeId} only={NUDGE_SCOPES} />
          </td>
        </tr>
      )}
    </>
  );
}

export default function Queue() {
  const ward = useCareWard();
  const { patients, nowMs, role } = ward;
  const [openKey, setOpenKey] = useState(null);
  const rows = queueRows(patients, role, nowMs);
  const handovers = role === "nurse" ? patients.filter((p) => p.view.handover) : [];
  return (
    <>
      <PageLead kicker="Ward" title="My queue" body="What is waiting on you, longest wait first." />
      {role === "doctor" && (
        <div className="row" role="group" aria-label="My status">
          <span className="label">My status</span>
          {STATUS_CHOICES.map((choice) => (
            <button key={choice.id} type="button" disabled={ward.busy} onClick={() => ward.setDoctorStatus(choice)}>{choice.label}</button>
          ))}
          <Fault fault={ward.fault} episodeId={null} only={[STATUS]} />
        </div>
      )}
      {rows.length ? (
        <div className="card table-box">
          <table>
            <thead>
              <tr>
                <th>Bed</th>
                <th className="left">Patient</th>
                <th>What</th>
                <th>Waited</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <QueueRow
                  key={row.key}
                  row={row}
                  ward={ward}
                  open={openKey === row.key}
                  toggle={() => setOpenKey(openKey === row.key ? null : row.key)}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">Nothing needs you now.</p>
      )}
      {handovers.map((p) => (
        <div className="card" key={p.id}>
          <Link to={`/chart/${p.id}`}>Handover: Bed {p.bed}, {p.name} →</Link>
        </div>
      ))}
      <h2>My patients</h2>
      <ul className="patient-list">
        {patients.map((p) => (
          <li key={p.id}>
            <Link to={`/chart/${p.id}`}>
              <span className="num">Bed {p.bed}</span>
              <span>{p.name}</span>
              <StateBadge patient={p} />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

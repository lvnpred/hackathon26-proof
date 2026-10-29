import { useState } from "react";
import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { Nudge } from "../screens/WardPanel";
import { DEMO, useCareWard } from "./CareShell";
import { queueRows } from "./derive";
import { stageFor } from "./Patients";

function QueueRow({ row, ward, open, toggle }) {
  const patient = ward.find(row.episodeId);
  const nudge = (patient?.view.nudges || []).find((n) => n.id === row.lineId);
  const to = row.lineId
    ? `/chart/${row.episodeId}?line=${row.lineId}`
    : `/chart/${row.episodeId}${row.stage ? `?stage=${row.stage}` : ""}`;
  return (
    <>
      <tr>
        <td className="num">Bed {row.bed}</td>
        <td>{row.name}</td>
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
      {rows.length ? (
        <div className="card table-box">
          <table>
            <thead>
              <tr>
                <th>Bed</th>
                <th>Patient</th>
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
          <Link to={`/chart/${p.id}?stage=ward`}>Handover: Bed {p.bed}, {p.name} →</Link>
        </div>
      ))}
      <h2>My patients</h2>
      <ul className="patient-list">
        {patients.map((p) => (
          <li key={p.id}>
            <Link to={`/chart/${p.id}`}>
              <span className="num">Bed {p.bed}</span>
              <span>{p.name}</span>
              <span className="pill">{stageFor(p, nowMs)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

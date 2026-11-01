import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageLead } from "../App";
import { DEMO, useCareWard } from "./CareShell";
import Fault from "./Fault";
import LoadError from "./LoadError";
import { NUDGE_SCOPES } from "./faults";
import AlertCard from "./AlertCard.jsx";
import { SAFETY } from "./alerts";
import { queueRows } from "./derive";
import { opensOnKey, opensRow } from "./rows";

function QueueRow({ row, ward, open, toggle }) {
  const patient = ward.find(row.episodeId);
  const nudge = (patient?.view.nudges || []).find((n) => n.id === row.lineId);
  const to = `/chart/${row.episodeId}${row.lineId ? `?line=${row.lineId}` : ""}`;
  const navigate = useNavigate();
  return (
    <>
      <tr
        className="row-link"
        tabIndex={0}
        onClick={(e) => opensRow(e.target) && navigate(to)}
        onKeyDown={(e) => opensOnKey(e) && navigate(to)}
        aria-label={`Open chart: Bed ${row.bed}, ${row.name}`}
      >
        <td className="num">Bed {row.bed}</td>
        <td className="left">{row.name}</td>
        <td>{row.staffSays || row.says}</td>
        <td>{row.waited}</td>
        <td>
          {DEMO && nudge && <button onClick={toggle}>{open ? "Close" : "Answer"}</button>} <Link to={to} tabIndex={-1}>Open →</Link>
        </td>
      </tr>
      {open && nudge && (
        <tr>
          <td colSpan={5}>
            <AlertCard view={patient.view} role={ward.role} nudge={nudge} safety={SAFETY.includes(nudge.kind)} primary busy={ward.busy} act={(path, body) => ward.act(row.episodeId, path, body)} nowMs={ward.nowMs} episodeId={row.episodeId} />
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
      <LoadError patients={patients} error={ward.loadError} />
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
    </>
  );
}

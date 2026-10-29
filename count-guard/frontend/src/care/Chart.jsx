import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getAudit } from "../journey";
import { AuditTable } from "../screens/Audit";
import ClinicPanel from "../screens/ClinicPanel";
import { CheckIn, MyCard } from "../screens/PatientCard";
import WardPanel from "../screens/WardPanel";
import { useCareWard } from "./CareShell";
import { stageOf } from "./clock";
import TheatrePanel from "./TheatrePanel";
import Timeline, { LENSES } from "./Timeline";

const STAGES = [["clinic", "Clinic"], ["theatre", "Theatre"], ["ward", "Ward"], ["home", "Home"]];
const ORDER = STAGES.map(([id]) => id);
const LENS_CHIPS = [["nurse", "Nurse"], ["doctor", "Doctor"], ["patient", "Patient"], ["everyone", "Everyone (audit)"]];

// The latest count.closing that no later line replaced, read from the audit rows (they carry replaced_by).
function theatreFact(rows, failed) {
  if (failed) return "count unknown";
  const closing = rows.filter((row) => row.type === "count.closing" && !row.replaced_by).pop();
  const match = closing?.what.match(/opened (\d+), back (\d+)/);
  return match ? `count ${match[2]}/${match[1]}` : "no count yet";
}

function facts(view, rows, failed) {
  const handover = view.handover;
  return {
    clinic: view.rx ? `${view.rx.rows.length} medicines` : "no prescription",
    theatre: theatreFact(rows, failed),
    ward: handover ? (handover.accepted_by ? "handover accepted" : "handover drafted") : view.orders ? "orders set" : "no orders",
    home: view.card ? "card signed" : "no card yet",
  };
}

// The four stages. Without onPick the bar is plain text (My care); with it each stage is a button.
export function StageBar({ now, facts: fact, stage, onPick }) {
  return (
    <ol className="stage-bar" aria-label="Stages">
      {STAGES.map(([id, name], index) => {
        const state = index < now ? "done" : index === now ? "now" : "later";
        const body = (
          <>
            <b>{name}</b>
            <span className="small">{state}{fact[id] ? ` · ${fact[id]}` : ""}</span>
          </>
        );
        return (
          <li key={id}>
            {onPick ? (
              <button type="button" className={`stage-btn ${state}`} aria-pressed={stage === id} onClick={() => onPick(id)}>{body}</button>
            ) : (
              <div className={`stage-btn ${state}`} aria-current={state === "now" ? "step" : undefined}>{body}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function HomePanel({ view, busy, act }) {
  const lines = view.timeline.filter((item) => item.type.startsWith("checkin.") || item.type.startsWith("help."));
  return (
    <>
      <MyCard card={view.card} busy={busy} act={act} />
      {view.card && <CheckIn card={view.card} busy={busy} act={act} />}
      <section className="card">
        <p className="label">Check-ins and help lines</p>
        {lines.length === 0 && <p className="empty small">No check-ins or help requests yet.</p>}
        {lines.map((item) => <p className="small" key={item.id}><span className="tag">{item.when}</span> {item.plain}</p>)}
      </section>
    </>
  );
}

export default function Chart() {
  const { episodeId } = useParams();
  const [params] = useSearchParams();
  const ward = useCareWard();
  const patient = ward.find(episodeId);
  const view = patient?.view;
  const line = params.get("line");
  const [stage, setStage] = useState(() => (ORDER.includes(params.get("stage")) ? params.get("stage") : null));
  const [picked, setPicked] = useState(null);
  const [rows, setRows] = useState([]);
  const [rowsError, setRowsError] = useState("");
  const lens = picked || ward.role;
  const stamp = view?.timeline.length;

  // Audit rows feed the Theatre fact, the struck lines and the Everyone lens; refetch when the record grows.
  useEffect(() => {
    if (!patient) return undefined;
    let live = true;
    getAudit(episodeId)
      .then((audit) => { if (live) { setRows(audit.rows); setRowsError(""); } })
      .catch((exc) => { if (live) setRowsError(exc.message); });
    return () => { live = false; };
  }, [episodeId, Boolean(patient), stamp]);

  useEffect(() => {
    const wanted = params.get("stage");
    if (ORDER.includes(wanted)) setStage(wanted);
  }, [params]);

  // A missing id leaves the chart at the top.
  useEffect(() => {
    if (!line || !view) return;
    const target = document.querySelector(`[data-line="${CSS.escape(line)}"]`);
    if (target) target.scrollIntoView({ block: "center" });
  }, [line, Boolean(view)]);

  if (!ward.patients.length) return <p className="empty">{ward.error || "Loading the ward…"}</p>;
  if (!patient) {
    return <p className="empty">No patient with that id. <Link to="/patients">Back to patients</Link></p>;
  }

  const now = ORDER.indexOf(stageOf(ward.nowMs));
  const fact = facts(view, rows, Boolean(rowsError));
  const act = (path, body) => ward.act(episodeId, path, body);
  const replaced = new Set(rows.filter((row) => row.replaced_by).map((row) => row.id));
  const procedure = view.card?.title || view.rx?.diagnosis?.join(", ");

  return (
    <>
      <header className="page-head">
        <p className="label">Bed {patient.bed}</p>
        <h1>{patient.name}</h1>
        {procedure && <p>{procedure}</p>}
      </header>

      <StageBar now={now} facts={fact} stage={stage} onPick={(id) => setStage(stage === id ? null : id)} />

      {stage === "clinic" && <ClinicPanel view={view} busy={ward.busy} act={act} />}
      {stage === "theatre" && <TheatrePanel episodeId={episodeId} view={view} busy={ward.busy} act={act} replaced={replaced} />}
      {stage === "ward" && <WardPanel view={view} busy={ward.busy} act={act} />}
      {stage === "home" && <HomePanel view={view} busy={ward.busy} act={act} />}

      <div className="row" role="group" aria-label="Lens">
        {LENS_CHIPS.map(([id, name]) => (
          <button key={id} type="button" className="pill" aria-pressed={lens === id} onClick={() => setPicked(id)}>{name}</button>
        ))}
      </div>

      <section className="card">
        <p className="label">Timeline</p>
        {lens === "everyone" ? (
          rowsError ? <p className="error" role="alert">Could not load the audit lines: {rowsError}</p>
          : rows.length ? <AuditTable rows={rows} /> : <p className="empty small">Nothing recorded for this patient yet.</p>
        ) : (
          <Timeline
            lines={view.timeline}
            nudges={view.nudges}
            replaced={replaced}
            lens={lens in LENSES ? lens : "nurse"}
            role={ward.role}
            line={line}
            busy={ward.busy}
            act={act}
          />
        )}
      </section>
    </>
  );
}

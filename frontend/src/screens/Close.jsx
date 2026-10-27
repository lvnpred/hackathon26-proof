import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { closeCase, discrepancies, health, resolveDiscrepancy } from "../api";
import { Models, Shell } from "../App";
import { loadEpisode, send } from "../episode";

export default function Close() {
  const { caseId } = useParams();
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState(null);
  const [reason, setReason] = useState("Found under drape, placed in bucket");
  const [by, setBy] = useState("demo user");
  const [result, setResult] = useState(null);
  const [patient, setPatient] = useState(null);
  const [filed, setFiled] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    const body = await discrepancies(caseId);
    setRows(body.discrepancies);
  }

  useEffect(() => {
    load().catch((exc) => setError(exc.message));
    health().then(setStatus).catch(() => setStatus(null));
    loadEpisode().then(setPatient).catch(() => setPatient(null));
  }, [caseId]);

  async function resolve(id) {
    setError("");
    try {
      await resolveDiscrepancy(id, reason, by);
      setResult(null);
      await load();
    } catch (exc) {
      setError(exc.message);
    }
  }

  async function fileOnPatient() {
    setError("");
    try {
      setFiled(
        await send(`/morning/episodes/${patient.episode.id}/count/from-case`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ case_id: caseId }),
        }),
      );
    } catch (exc) {
      setError(exc.message);
    }
  }

  async function close() {
    setError("");
    try {
      setResult(await closeCase(caseId));
    } catch (exc) {
      setResult(null);
      setError(exc.body?.detail?.message || exc.message);
    }
  }

  const openHard = rows.filter((row) => row.status === "open" && row.rule_id !== "R5");

  return (
    <Shell>
      <Models health={status} />
      <p><Link to={`/case/${caseId}`}>Back to the live case</Link></p>
      <div className="layout">
        <section className="sheet">
          <h2>4. Close and report</h2>
          <p>The case closes as reconciled only when rules R1 to R4 have no open items, or a person records a reason for each one. A low-confidence look does not block closing.</p>
          {rows.map((row) => (
            <article className="alert" key={row.id}>
              <b>{row.status}</b> · {row.rule_id} · {row.kind} · {row.item_type}
              <small>{row.detail}</small>
              {row.resolution && (
                <small>Resolved by {row.resolution.by}: {row.resolution.reason}</small>
              )}
              {row.status === "open" && row.blocks_closing !== false && row.rule_id !== "R5" && (
                <button onClick={() => resolve(row.id)}>Record resolution</button>
              )}
            </article>
          ))}
          <label>
            Reason
            <input value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <label>
            Recorded by
            <input value={by} onChange={(event) => setBy(event.target.value)} />
          </label>
          <div className="row">
            <button onClick={close}>Run closing gate</button>
            <span className="clock">{openHard.length} open hard alert{openHard.length === 1 ? "" : "s"}</span>
          </div>
          {error && <p className="error">{error}</p>}
          <h2>File it on this patient</h2>
          <p>
            The camera count stays on this case until you file it.
            Filing writes the ledger onto {patient?.episode?.label || "the current patient"} and does not mix it with another morning.
          </p>
          <button onClick={fileOnPatient} disabled={!patient}>File on this patient</button>
          {filed?.already_filed && <p>Already filed on this patient.</p>}
          {filed?.filed && (
            <p>
              Filed. Opened {filed.sheet.count.opened}, back {filed.sheet.count.returned}, unaccounted {filed.sheet.count.unaccounted}.{" "}
              <Link to="/ward">Read the discharge sheet</Link>
            </p>
          )}
        </section>
        <section className="panel">
          <h2>Count sheet</h2>
          {!result && <p>The PDF is written when the gate passes.</p>}
          {result && (
            <>
              <p className="clock">Narrative model: {result.model}</p>
              <p>{result.narrative}</p>
              {result.trace?.length > 0 && (
                <p className="clock">Tools: {result.trace.map((call) => call.tool).join(", ")}</p>
              )}
              <p><a href={result.report_url}>Open the PDF count sheet</a></p>
            </>
          )}
        </section>
      </div>
    </Shell>
  );
}

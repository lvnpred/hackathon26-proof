import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { TITLES, closeCase, discrepancies, health, resolveDiscrepancy } from "../api";
import { Models, Shell } from "../App";
import { loadEpisode, send } from "../episode";
import { getJourney } from "../journey";

// The chart's "Count by camera" tied its patient to this case when Setup made it; storage can throw.
function chartEpisode(caseId) {
  try {
    return sessionStorage.getItem(`cg-chart:${caseId}`) || "";
  } catch {
    return "";
  }
}

const EXAMPLE = "For example: found under drape, placed in bucket";

export default function Close() {
  const { caseId } = useParams();
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState(null);
  const [reasons, setReasons] = useState({});
  const [by, setBy] = useState("demo user");
  const [result, setResult] = useState(null);
  const [patient, setPatient] = useState(null);
  const [chartLabel, setChartLabel] = useState("");
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
    const chart = chartEpisode(caseId);
    if (chart) getJourney(chart).then((view) => setChartLabel(view.episode?.label || "")).catch(() => setChartLabel(""));
  }, [caseId]);

  async function resolve(id) {
    setError("");
    const reason = (reasons[id] || "").trim();
    if (!reason) {
      setError("Write the reason for this item first.");
      return;
    }
    try {
      await resolveDiscrepancy(id, reason, by);
      setResult(null);
      await load();
    } catch (exc) {
      setError(exc.message);
    }
  }

  const chartId = chartEpisode(caseId);
  const targetId = chartId || patient?.episode?.id;

  async function fileOnPatient() {
    setError("");
    try {
      setFiled(
        await send(`/morning/episodes/${targetId}/count/from-case`, {
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

  const blocks = (row) => row.status === "open" && row.blocks_closing !== false && row.rule_id !== "R5";
  const openHard = rows.filter(blocks);
  const resolved = rows.filter((row) => row.resolution);
  const label = (chartId ? chartLabel : patient?.episode?.label) || "the current patient";

  return (
    <Shell
      subtitle="Camera count · close and report"
      status={openHard.length ? { tone: "record", label: `${openHard.length} open` } : { tone: "ready", label: "Ready to close" }}
    >
      <div className="row between">
        <Link to={`/case/${caseId}`}>← Back to the live case</Link>
        <Models health={status} />
      </div>

      <div className="split">
        <section className="main">
          <header className="page-head">
            <p className="label">Close and report</p>
            <h1>
              {openHard.length
                ? `${openHard.length} item${openHard.length === 1 ? " needs" : "s need"} a reason before the case closes`
                : "Nothing blocks closing"}
            </h1>
            <p>The case closes as reconciled only when rules R1 to R4 have no open items, or a person records a reason for each one. A low-confidence look does not block closing.</p>
          </header>
          {error && <p className="error" role="alert">{error}</p>}

          {rows.map((row) => (
            <article className={`alert-card${blocks(row) ? " open" : ""}`} key={row.id}>
              <div className="row between" style={{ alignItems: "flex-start" }}>
                <div className="stack" style={{ gap: 2, minWidth: 0, flex: "1 1 240px" }}>
                  <h2>{TITLES[row.kind] || row.kind}</h2>
                  <p>{row.detail}</p>
                  <p className="muted" style={{ fontSize: 12, fontWeight: 700 }}>
                    {row.rule_id} · {row.kind.replaceAll("_", " ")} · {row.item_type}
                  </p>
                </div>
                <span className={`pill ${row.resolution ? "ready" : blocks(row) ? "record" : "info"}`}>
                  {row.resolution ? "Resolved" : row.status === "open" ? (blocks(row) ? "Open" : "Look only") : row.status}
                </span>
              </div>
              {row.resolution && (
                <p className="small">Resolved by <b>{row.resolution.by}</b>: {row.resolution.reason}</p>
              )}
              {blocks(row) && (
                <div className="row" style={{ alignItems: "flex-end" }}>
                  <label className="field" style={{ flex: "1 1 280px" }}>
                    Reason
                    <input
                      value={reasons[row.id] || ""}
                      placeholder={EXAMPLE}
                      onChange={(event) => setReasons({ ...reasons, [row.id]: event.target.value })}
                    />
                  </label>
                  <button onClick={() => resolve(row.id)}>Record reason</button>
                </div>
              )}
            </article>
          ))}
          {rows.length === 0 && <p className="empty">No alerts on this case.</p>}

          <div className="card sunk">
            <div className="row" style={{ alignItems: "flex-end" }}>
              <label className="field" style={{ flex: "1 1 240px" }}>
                Recorded by
                <input value={by} onChange={(event) => setBy(event.target.value)} />
              </label>
              <div className="stack" style={{ gap: 6 }}>
                <span className="num small" style={{ fontWeight: 700, color: openHard.length ? "var(--record)" : "var(--leaf)" }}>
                  {openHard.length ? `${openHard.length} open · closing is blocked` : "No open hard alerts"}
                </span>
                <button className="primary" onClick={close}>Run closing gate</button>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="row between">
              <div className="stack" style={{ gap: 2, flex: "1 1 320px" }}>
                <h2>File it on this patient</h2>
                <p className="muted small">
                  The camera count stays on this case until you file it.
                  Filing writes the ledger onto {label} and does not mix it with another morning.
                </p>
              </div>
              <button onClick={fileOnPatient} disabled={!targetId}>File on this patient</button>
            </div>
            {filed?.already_filed && <p className="small">Already filed on this patient.</p>}
            {filed?.filed && (
              <p className="small">
                Filed. Opened {filed.sheet.count.opened}, back {filed.sheet.count.returned}, unaccounted {filed.sheet.count.unaccounted}.{" "}
                {chartId && <><Link to={`/chart/${chartId}`}>Back to the chart</Link>{" "}</>}
                <Link to="/ward">Read the discharge sheet</Link>
              </p>
            )}
          </div>
        </section>

        <aside className="side">
          <p className="label">Count sheet</p>
          <article className="paper">
            <header className="paper-head">
              <p className="paper-letter">Count Guard · research demo</p>
              <h2 className="paper-title">Surgical count sheet</h2>
            </header>
            <section>
              <h3>Open items</h3>
              {openHard.length ? (
                <p>{openHard.map((row) => row.rule_id).join(", ")}, no reason recorded yet</p>
              ) : (
                <p className="blank">None</p>
              )}
            </section>
            <section>
              <h3>Resolved</h3>
              {resolved.length ? (
                resolved.map((row) => (
                  <p key={row.id}>{row.rule_id}: resolved by {row.resolution.by}: {row.resolution.reason}</p>
                ))
              ) : (
                <p className="blank">None yet</p>
              )}
            </section>
            <section>
              <h3>Narrative</h3>
              {result ? (
                <>
                  <p>{result.narrative}</p>
                  <p className="blank">Narrative model: {result.model}</p>
                  {result.trace?.length > 0 && (
                    <p className="blank">Tools: {result.trace.map((call) => call.tool).join(", ")}</p>
                  )}
                </>
              ) : (
                <p className="blank">The PDF is written when the gate passes.</p>
              )}
            </section>
            {result && <a className="button primary" href={result.report_url}>Open the PDF count sheet</a>}
          </article>
        </aside>
      </div>
    </Shell>
  );
}

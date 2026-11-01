import { useState } from "react";
import { closingBody } from "./capture";
import AiMark from "./AiMark.jsx";
import { displayName } from "./names";
import { countReconciled, packLine, savedLine, swabFigures } from "./theatre";
import VideoCheck from "./VideoCheck";
import { momentFor } from "./moments.js";
import { latestCheck, swabTotal } from "./video";

const NURSE = "Nurse Asha (synthetic)";

// The swab count: pack opened, what the camera read, the number the nurse types, and a save by a person.
export default function CountPanel({ episodeId, view, busy, act, upload, replaced, onNote }) {
  const [quantity, setQuantity] = useState(String(swabTotal(view) ?? "20"));
  const [returned, setReturned] = useState("");
  const [detail, setDetail] = useState("");
  const [changing, setChanging] = useState(false);
  const by = NURSE; // the tagged value goes to the server; the screen shows the plain name

  const count = view.count;
  const open = (view?.nudges || []).find((nudge) => nudge.kind === "count_open");
  const corrected = open && replaced?.has(open.fact_id);
  const ready = view && !busy;
  const opened = Number(quantity);
  const back = Number(returned);
  const validBack = returned !== "" && Number.isInteger(back) && back >= 0;
  const camera = count?.camera ? count.camera.count : null;
  const packed = count?.opened != null;
  const unaccounted = packed && validBack ? count.opened - back : null;
  // The server asks for a reason when the numbers do not add up; the panel also asks when the nurse's number is not the camera's.
  const needsReason = (unaccounted !== null && unaccounted !== 0) || (validBack && camera != null && back !== camera);
  const missing = unaccounted ?? count?.missing ?? null;
  const figures = swabFigures({ opened: count?.opened, returned: validBack ? back : count?.returned, missing });
  const swabCheck = latestCheck(view, "swabs");
  const thisStay = swabCheck && (count?.opened_at_ms == null || swabCheck.at_ms >= count.opened_at_ms) ? swabCheck : null;
  const complete = countReconciled(view);
  const askPack = !packed || changing;

  async function post(body) {
    onNote("");
    return act("/count", { ...body, by });
  }

  async function save(supersedesId) {
    const body = closingBody(count, back, detail.trim());
    if (supersedesId) body.supersedes_id = supersedesId;
    if (await post(body)) {
      setReturned("");
      setDetail("");
      onNote(supersedesId ? "Count corrected." : "");
    }
  }

  const canSave = ready && packed && validBack && (!needsReason || detail.trim() !== "");

  return (
    <section className="swab-panel" aria-label="Swab count">
      <div className="swab-figures">
        {[["opened", "Opened"], ["back", "Back"], ["missing", "Unaccounted"]].map(([key, name]) => (
          <p key={key}>
            <span className={`t-display ${key === "missing" && missing != null && missing !== 0 ? "s-danger" : ""}`}>{figures[key]}</span>
            <span className="t-caption muted">{name}{key === "missing" ? " · Worked out, not typed" : ""}</span>
          </p>
        ))}
      </div>
      {complete && <p className="note" role="status">Count complete</p>}
      {packed && <p className="small">{packLine(count)} {!changing && <button type="button" className="quiet" onClick={() => setChanging(true)}>change</button>}</p>}
      {askPack && (
        <div className="row">
          <label className="field" style={{ flex: "1 1 120px" }}>
            Pack opened
            <input inputMode="numeric" value={quantity} onChange={(event) => setQuantity(event.target.value)} />
          </label>
          <p className="small muted" style={{ flex: "1 1 160px" }}>By {displayName(by)}</p>
          <button
            disabled={!ready || !Number.isInteger(opened) || opened < 1}
            onClick={async () => {
              if (await post({ step: "opened", quantity: opened })) {
                setChanging(false);
                onNote("Pack opened recorded.");
              }
            }}
          >
            Record pack opened
          </button>
        </div>
      )}
      <div className="row">
        <label className="field" style={{ flex: "1 1 120px" }}>
          Closing count (returned)
          <input inputMode="numeric" value={returned} onChange={(event) => setReturned(event.target.value)} />
        </label>
        {camera != null && <p className="small" style={{ flex: "1 1 120px" }}><AiMark /> Camera read {camera}</p>}
        <label className="field" style={{ flex: "2 1 220px" }}>
          What did the team do?{needsReason ? " (required)" : ""}
          <input value={detail} onChange={(event) => setDetail(event.target.value)} placeholder="Found under the drape" />
        </label>
        <button className="primary" disabled={!canSave} onClick={() => save(null)}>Save count as {displayName(by)}</button>
        {open && !corrected && (
          <button disabled={!canSave} onClick={() => save(open.fact_id)}>Correct the count</button>
        )}
      </div>
      {savedLine(count) && <p className="small" role="status">{savedLine(count)}</p>}
      {packed && (
        <VideoCheck
          title="Swab camera count"
          kind="swabs"
          episodeId={episodeId}
          version={view.timeline?.length}
          check={thisStay}
          moment={momentFor(view, thisStay?.id)}
          busy={busy}
          onFile={(file) => upload("/video", file, { check: "swabs", by })}
        />
      )}
    </section>
  );
}

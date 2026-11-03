import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { call } from "../journey";
import { Evidence } from "./Evidence.jsx";
import { PARTS, expandParts, recordUrl } from "./expandModel.js";
import "./expand.css";
import "./provenance.css";

// The Expand view of one model result (clarity §4.2): Captured, Model returned, How the app used it, What a person
// did. `record` is the result in hand (a heard recording, a sample try, a camera read); `record.eventId` names the event
// to read back (GET …/events/{id}/model), whose evidence then fills the parts. Images and frames reuse the evidence
// viewer (Evidence -> EvidenceExpand, with its boxes); this view adds the audio, the text, the model and the people.
// Demo-scan contract (scan.mjs): the open view's root carries data-expand="open" (model names may show inside it on a
// staff screen); the button that opens it carries data-expand="closed". The patient lens names no model (expandModel.js).
export function ModelExpand({ record, view, lens = "staff", title = "Model result", onClose }) {
  const episodeId = view?.episode?.id || record?.episode_id;
  const eventId = record?.eventId;
  const [fetched, setFetched] = useState({ id: null, data: null, error: "" });
  const close = useRef(null);
  useEffect(() => {
    if (!eventId || !episodeId) return undefined;
    let live = true;
    call(recordUrl(episodeId, eventId, lens))
      .then((data) => live && setFetched({ id: eventId, data, error: "" }))
      .catch((exc) => live && setFetched({ id: eventId, data: null, error: exc.message || "Not found" }));
    return () => { live = false; };
  }, [episodeId, eventId, lens]);
  useEffect(() => {
    close.current?.focus();
    const key = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);
  const waiting = Boolean(eventId && episodeId) && fetched.id !== eventId; // no episode: the record is shown as it is
  // The event read back fills the parts; a record that names its own type (a camera count read) keeps it.
  const full = fetched.id === eventId && fetched.data ? { ...record, ...fetched.data, type: record.type || fetched.data.type } : record;
  const parts = expandParts(full, view, lens);
  const body = { captured: Captured, returned: Returned, used: Used, people: People };
  return createPortal(
    <div className="ev-modal" data-expand="open" role="dialog" aria-modal="true" aria-label={`${title}, expanded`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ev-modal-body card mx-body">
        <div className="ev-modal-head">
          <p className="label">{title}</p>
          <button ref={close} type="button" onClick={onClose}>Close ✕</button>
        </div>
        {waiting && <p className="small muted" role="status">Loading what was captured…</p>}
        {fetched.error && <p className="note small" role="alert">Could not load the full record: {fetched.error}</p>}
        {PARTS.map(({ key, title: heading }) => {
          const Part = body[key];
          return (
            <section key={key} className="mx-part" aria-label={heading}>
              <h3>{heading}</h3>
              <Part part={parts[key]} record={full} episodeId={episodeId} lens={lens} />
            </section>
          );
        })}
      </div>
    </div>,
    document.body,
  );
}

function Captured({ part, record, episodeId, lens }) {
  const any = record?.sample || part.audio || part.transcript || part.photo || part.evidenceId || part.facts.length || part.sent || part.note || part.expect;
  return (
    <>
      {part.note && <p>{part.note}</p>}
      {part.audio && <audio controls preload="none" src={part.audio} aria-label="The recording" />}
      {part.transcript && <p>{part.typed ? "Typed" : "Heard"}: <q>{part.transcript}</q></p>}
      {part.answer && <p>Confirmed: <q>{part.answer}</q></p>}
      {part.photo && <img className="mx-photo" src={part.photo} alt="The photo that was checked" />}
      {record?.sample && <Evidence sample={record.sample} check={{ rows: record.sample.rows }} linkLines={false} />}
      {part.evidenceId && episodeId && <Evidence episodeId={episodeId} evidenceId={part.evidenceId} check={record?.frames ? record : undefined} linkLines={false} />}
      {part.expect && <p className="small">Checked for: {part.expect}</p>}
      {part.facts.length > 0 && <ul className="small">{part.facts.map((f, i) => <li key={i}>{f}</li>)}</ul>}
      {part.sent && <details><summary>Text sent</summary><pre>{part.sent}</pre></details>}
      {!any && <p className="small muted">{lens === "patient" ? "Nothing kept to show." : "Nothing kept for this result."}</p>}
    </>
  );
}

function Returned({ part }) {
  return (
    <>
      <p>
        {part.model && <strong>{part.model} · </strong>}
        {part.modeText}
        {part.seconds && <span className="muted"> · {part.seconds}</span>}
      </p>
      {part.calls.length > 1 && (
        <ul className="small">
          {part.calls.map((c, i) => <li key={i}>{c.model} · {c.modeText}{c.seconds ? ` · ${c.seconds}` : ""}</li>)}
        </ul>
      )}
      {part.raw && <details><summary>Raw reply</summary><pre>{part.raw}</pre></details>}
    </>
  );
}

function Used({ part }) {
  return (
    <>
      {part.lines.length > 0 ? <ul>{part.lines.map((line, i) => <li key={i}>{line}</li>)}</ul> : <p className="small muted">Nothing was read from it.</p>}
      {part.fallback && <p className="note small">{part.fallback}</p>}
    </>
  );
}

function People({ part }) {
  if (!part) return <p className="small muted">Nothing for a person to answer.</p>;
  return (
    <>
      <p><span className={part.kind === "proposed" ? "prov prov-proposed" : "prov prov-accepted"}>{part.text}</span></p>
      {part.lines?.length > 0 && <ul className="small">{part.lines.map((line, i) => <li key={i}>{line}</li>)}</ul>}
      {part.note && <p className="small muted">{part.note}</p>}
      {part.reason && <p className="small">Reason: {part.reason}</p>}
      {(part.before || part.after) && (
        <dl className="mx-change small">
          <dt>Before</dt><dd>{part.before || "—"}</dd>
          <dt>After</dt><dd>{part.after || "—"}</dd>
        </dl>
      )}
    </>
  );
}

// An Expand button and the view it opens. `record` is the result, or { eventId } of the event to read back.
export function ExpandButton({ record, view, lens = "staff", title, label = "Expand" }) {
  const [open, setOpen] = useState(false);
  const shut = useCallback(() => setOpen(false), []);
  if (!record) return null;
  return (
    <>
      <button type="button" className="quiet" data-expand="closed" aria-haspopup="dialog" onClick={() => setOpen(true)}>{label}</button>
      {open && <ModelExpand record={record} view={view} lens={lens} title={title} onClose={shut} />}
    </>
  );
}

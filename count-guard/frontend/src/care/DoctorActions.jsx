import { useState } from "react";
import { RxImport, RxTable } from "./legacy/Rx";
import { heardHow } from "./askText";
import ActionBar from "./ActionBar";
import { IconMic } from "./icons.jsx";
import { panelOpen, toggled } from "./actions";
import { doctorBlocks, quietActions } from "./journey";
import NowCard from "./NowCard";
import Dictate from "./Dictate";
import AiMoment from "./AiMoment.jsx";
import { draftChanged } from "./drafts";
import { draftSummary, LEAVE_OUT, leftOutOf, notPlacedLine, pendingUnplaced, placeSentence } from "./dischargeDraft.js";
import DischargeDraft from "./DischargeDraft.jsx";
import Provenance from "./Provenance.jsx";
import { lastActOf, madeByModel, sameOrders } from "./provenance.js";
import { lastSigned, momentFor } from "./moments";
import OrderForm from "./OrderForm";
import UnplacedSentences from "./UnplacedSentences.jsx";
import TheatreChecklist from "./TheatreChecklist";
import { theatreSteps } from "./theatre";
import PhotoInput from "./PhotoInput.jsx";
import HomeMedicines from "./HomeMedicines.jsx";
import { TrayPreview } from "./VideoCheck";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN, outcomeOf, own } from "./stepOutcome.js";
import { ExpandButton } from "./ModelExpand.jsx";
import Opens from "./Opens.jsx";
import { gate } from "./visibility.js";

export const DOCTOR = "Dr. A. Rao (synthetic)";

// Hear a recording as text to check, then draft from that text. heard_by keeps who heard it; heard words the doctor
// edited stay voice (ruling P8), so the draft keeps its voice origin. `o` is the card's step opts: its fault is its own.
const hearing = (ask, path) => (file, o) => ask("/ask/hear", file, { by: DOCTOR }, path, own(o));
const draftFrom = (upload, path) => ({ text, heard }, o) =>
  upload(path, undefined, { text, by: DOCTOR, heard_by: heardHow(heard?.text, text, heard?.by).heard_by }, undefined, own(o));
// How Spark did on a draft: the open draft's evidence, else its moment; plain "Done" when neither says.
const draftOutcome = (kind) => (view) => {
  const draft = view?.drafts?.[kind];
  return outcomeOf(draft?.evidence ? draft : null) || outcomeOf(momentFor(view, draft?.id)) || UNKNOWN;
};
// The Expand record of a draft step: the open draft, read back by its event id (clarity §4.2).
const draftRecord = (kind) => (view) => (view?.drafts?.[kind] ? { ...view.drafts[kind], eventId: view.drafts[kind].id } : null);

function PhotoCard({ title, busy, upload }) {
  return (
    <section className="card" aria-label={title}>
      <p className="label">{title}</p>
      <PhotoInput disabled={busy} onFiles={([file]) => upload("/photos", file, { purpose: "reference", by: DOCTOR })} />
    </section>
  );
}

// Dictation, the order form that loads its draft, and the reference photo input. While a draft waits to be signed the
// order form sits under the Next card (OrderDraft) and the finished dictation box folds away (spec P3).
// Outside the order states the draft stays but Sign orders is disabled and says when it opens (clarity §4.4).
function OrderDraft({ view, busy, signOrders, said = false }) {
  const draft = view.drafts?.order;
  const shut = gate("orders", view.state).reason;
  return <>{!said && <Opens reason={shut} />}<OrderForm busy={busy || Boolean(shut)} onSign={signOrders} draft={draft} moment={momentFor(view, draft?.id)} episodeId={view.episode?.id} acts={view.acts} /></>;
}

function OrdersDictation({ view, busy: working, upload, ask, signOrders }) {
  const { reason } = gate("orders", view.state);
  const busy = working || Boolean(reason); // outside the order states the card stays and says when it opens
  const draft = view.drafts?.order;
  const signed = draft ? null : lastSigned(view.ai_moments, "orders");
  // The drafting step lives here, not in the Dictate box: once the draft exists the box moves into the fold and
  // remounts, and the done line (or a failure) must stay in sight.
  const drafting = useModelStep({ capability: "orders" });
  const dictate = <Dictate label="Dictate orders" capability="orders" verb="Draft orders" busy={busy} view={view} sendStep={drafting} sendOutcome={draftOutcome("order")} sendRecord={draftRecord("order")} onHear={hearing(ask, "/dictate/orders")} onSend={draftFrom(upload, "/dictate/orders")} />;
  const line = <div aria-busy={busyOf(drafting.step)}><ModelStep busy={busy} step={drafting.step} onRetry={drafting.retry} expand={{ view, title: "Order draft" }} /></div>;
  const more = draft && <p className="small"><ExpandButton record={{ eventId: draft.id }} view={view} title="Order draft" label="Expand the draft" /></p>;
  if (draft) return <>{line}{more}<details className="fold"><summary>Dictate again</summary><Opens reason={reason} />{dictate}</details></>;
  return (
    <>
      <Opens reason={reason} />
      {dictate}
      {line}
      {signed && <AiMoment moment={signed} role="doctor" episodeId={view.episode?.id} />}
      {signed && <p className="small"><Provenance item={{ id: signed.id, value: signed.refs?.items, same: sameOrders, ai: madeByModel(signed) }} events={view.acts} /> <ExpandButton record={{ eventId: signed.id }} view={view} title="Signed orders" /></p>}
      <OrderDraft view={view} busy={busy} signOrders={signOrders} said />
    </>
  );
}

// Action for the clinic card: admit the patient (primary while it is Now) or close the visit.
function Admit({ view, busy: working, act, primary }) {
  const shut = gate("admit", view.state).reason;
  const busy = working || Boolean(shut);
  const [reason, setReason] = useState("");
  const [reasonDraftId, setReasonDraftId] = useState(null);
  const draft = view.drafts?.order;
  if (draftChanged(reasonDraftId, draft)) {
    setReasonDraftId(draft.id);
    if (draft.reason) setReason(draft.reason);
  }
  return (
    <>
      <label className="field">
        Reason for admission
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="row">
        <button type="button" className={primary ? "primary" : undefined} disabled={busy || !reason.trim()} onClick={() => act("/state", { to: "admitting", by: DOCTOR, reason: reason.trim() })}>Admit</button>
        <button type="button" disabled={busy} onClick={() => act("/state", { to: "clinic_done", by: DOCTOR })}>Close visit</button>
      </div>
      <Opens reason={shut} />
    </>
  );
}

// The clinic cards that sit below the quiet row (R25).
function Clinic({ view, busy, act, upload }) {
  return (
    <>
      <section className="card">
        <p className="label">Prescription</p>
        <RxImport busy={busy} act={act} />
        <RxTable rx={view.rx} />
      </section>
      <HomeMedicines view={view} busy={busy} upload={upload} act={act} />
    </>
  );
}

// Primary action for the ward card: draft the discharge from the record, dictate changes, then sign the latest draft.
// The form keeps its text while closed.
function Discharge({ view, busy, act, upload, ask, open, onToggle, primary }) {
  const [summary, setSummary] = useState("");
  const [summaryDraftId, setSummaryDraftId] = useState(null);
  const [settled, setSettled] = useState({}); // unplaced sentence index -> the section chosen, or LEAVE_OUT (clarity §4.5)
  const [template, setTemplate] = useState("hernia-repair");
  const draft = view.drafts?.discharge;
  const signedDraft = draft ? null : lastActOf(view.acts, "discharge.signed");
  if (draftChanged(summaryDraftId, draft)) {
    setSummaryDraftId(draft.id);
    setSettled({});
    setSummary(draftSummary(draft));
  }
  const templates = Object.entries(view.templates || {});
  // Drafting and signing run on the ward; dictating runs in every admitted state (clarity §4.4).
  const shut = { draft: gate("dischargeDraft", view.state).reason, dictate: gate("dischargeDictate", view.state).reason, sign: gate("dischargeSign", view.state).reason };
  const drafter = useModelStep({ capability: "discharge" });
  const draftFromRecord = () => drafter.run((o) => act("/discharge/draft", { by: DOCTOR }, undefined, own(o)), { outcome: draftOutcome("discharge"), record: draftRecord("discharge") });
  // Sign waits until each dictated sentence no section took is placed or left out (clarity §4.5).
  const pending = summaryDraftId ? pendingUnplaced(draft?.unplaced, settled) : [];
  async function signDischarge() {
    // The draft's summary as proposed goes with the signing, so an edited summary reads "Changed by" (clarity §4.3).
    const proposed = summaryDraftId && draft ? { proposed_summary: draftSummary(draft) } : {};
    const leftOut = summaryDraftId ? leftOutOf(draft?.unplaced, settled) : [];
    const done = await act("/discharge/sign", { summary: summary.trim(), template, by: DOCTOR, draft_id: summaryDraftId || undefined, ...proposed, ...(leftOut.length ? { left_out: leftOut } : {}) });
    if (done) {
      setSummary("");
      setSummaryDraftId(null);
      setSettled({});
    }
  }
  return (
    <>
      <button type="button" className={primary && !draft && !shut.draft ? "primary" : undefined} disabled={busy || Boolean(shut.draft)} onClick={draftFromRecord}>Draft discharge</button>
      <Opens reason={shut.draft} />
      <div aria-busy={busyOf(drafter.step)}><ModelStep busy={busy} step={drafter.step} onRetry={drafter.retry} expand={{ view, title: "Discharge draft" }} /></div>
      <button type="button" aria-expanded={open} disabled={Boolean(shut.dictate)} onClick={onToggle}><IconMic />Dictate discharge</button>
      <Opens reason={shut.dictate} />
      {signedDraft && <p className="small">Discharge signed <Provenance item={{ id: signedDraft.ref }} events={view.acts} /> <ExpandButton record={{ eventId: signedDraft.ref }} view={view} title="Signed discharge" /></p>}
      {open && !shut.dictate && <Dictate label="Dictate discharge" capability="discharge" verb="Update draft" busy={busy} view={view} sendCapability="discharge" sendOutcome={draftOutcome("discharge")} sendRecord={draftRecord("discharge")} onHear={hearing(ask, "/dictate/discharge")} onSend={draftFrom(upload, "/dictate/discharge")} />}
      {(open || draft) && (
        <>
          <DischargeDraft draft={draft} episodeId={view.episode?.id} acts={view.acts} />
          <div>
            <p className="label">Discharge</p>
            {summaryDraftId && (
              <>
                {momentFor(view, draft?.id) && <AiMoment moment={momentFor(view, draft.id)} role="doctor" episodeId={view.episode?.id} />}
                <p className="note small" role="status">{draft?.timeline ? "Draft from the record." : "Draft from dictation."} Check the summary, then sign.</p>
                <p className="small"><Provenance item={{ id: summaryDraftId, ai: madeByModel(draft) }} events={view.acts} /> <ExpandButton record={{ eventId: summaryDraftId }} view={view} title="Discharge draft" /></p>
              </>
            )}
            <label className="field">
              Summary
              <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
            </label>
            <UnplacedSentences sentences={pending} busy={busy} onSettle={(index, text, choice) => {
              setSettled((was) => ({ ...was, [index]: choice }));
              if (choice !== LEAVE_OUT) setSummary((s) => placeSentence(s, choice, text));
            }} />
            <label className="field">
              Template
              <select value={template} onChange={(e) => setTemplate(e.target.value)}>
                {templates.length === 0 && <option value="hernia-repair">hernia-repair</option>}
                {templates.map(([key, title]) => <option key={key} value={key}>{title}</option>)}
              </select>
            </label>
            <button type="button" className={primary && (draft || summary.trim()) && !shut.sign ? "primary" : undefined} disabled={busy || !summary.trim() || Boolean(shut.sign) || pending.length > 0} onClick={signDischarge}>Sign discharge</button>
            <Opens reason={shut.sign} />
            {pending.length > 0 && <p className="note small" role="status">{notPlacedLine(pending.length)}</p>}
          </div>
        </>
      )}
    </>
  );
}

// Primary action for the ward card: pick the procedure and send the patient to theatre.
function SendToTheatre({ view, busy: working, act, primary }) {
  const { reason } = gate("theatre", view.state);
  const busy = working || Boolean(reason);
  const [procedure, setProcedure] = useState("");
  const procedures = Object.entries(view.procedures || {});
  return (
    <div>
      <label className="field">
        Procedure
        <select value={procedure} onChange={(e) => setProcedure(e.target.value)}>
          <option value="">Choose a procedure</option>
          {procedures.map(([key, title]) => <option key={key} value={key}>{title}</option>)}
        </select>
      </label>
      <TrayPreview plan={view.tray_templates?.[procedure]} />
      <button type="button" className={primary && !reason ? "primary" : undefined} disabled={busy || !procedure} onClick={() => act("/state", { to: "theatre", by: DOCTOR, procedure })}>Send to theatre</button>
      <Opens reason={reason} />
    </div>
  );
}

// Outside theatre the card stays and says when it opens; its checklist reads the theatre record, so it waits.
function Theatre({ view, busy, act, upload, ask, nowMs }) {
  const shut = gate("theatreRoom", view.state).reason;
  if (shut) return <section className="card" aria-label="Theatre"><p className="label">Theatre checklist</p><Opens reason={shut} /></section>;
  return <TheatreOpen view={view} busy={busy} act={act} upload={upload} ask={ask} nowMs={nowMs} />;
}

function TheatreOpen({ view, busy, act, upload, ask, nowMs }) {
  const [reason, setReason] = useState("");
  const ended = theatreSteps(view)[3].done;
  const move = (view.allowed || []).find((m) => m.to === "ward" && m.role === "doctor");
  return (
    <>
      <TheatreChecklist role="doctor" view={view} busy={busy} act={act} upload={upload} ask={ask} nowMs={nowMs} />
      {move && (
        <section className="card">
          <label className="field">
            Reason for leaving the count open
            <input value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          {move.needs.filter((need) => !need.startsWith("reason")).length > 0 && (
            <p className="small muted">Needs: {move.needs.filter((need) => !need.startsWith("reason")).join(", ")}</p>
          )}
          <button
            type="button"
            disabled={busy || !ended || !reason.trim()}
            onClick={() => act("/state", { to: "ward", by: DOCTOR, reason: reason.trim(), checklist: {} })}
          >
            Back to ward
          </button>
        </section>
      )}
    </>
  );
}

const BLOCK_TITLE = { admit: "Admission", theatre: "Send to theatre", discharge: "Discharge" };
const sign = (act) => (items, draftId) => act("/orders/sign", { items, by: DOCTOR, draft_id: draftId || undefined });

// The doctor's actions for the patient's current state: the card, the quiet row, the open panels, the rest.
export default function DoctorActions({ state, card, pick, control, view, act, upload, ask, busy, nowMs, afterNow = null }) {
  const [chosen, setChosen] = useState(() => new Set());
  const signOrders = sign(act);
  const open = (id) => panelOpen(chosen, id, view);
  const toggle = (id) => setChosen((current) => toggled(current, id));
  // A block is primary only inside the Now card while the step is Now; otherwise it is a secondary button.
  const blocks = (primary) => ({
    admit: <Admit key="admit" view={view} busy={busy} act={act} primary={primary} />,
    theatre: <SendToTheatre key="theatre" view={view} busy={busy} act={act} primary={primary} />,
    discharge: <Discharge key="discharge" view={view} busy={busy} act={act} upload={upload} ask={ask} open={open("discharge")} onToggle={() => toggle("discharge")} primary={primary} />,
  });
  const { inside, below } = doctorBlocks(state, card);
  return (
    <>
      <NowCard pick={pick} card={card} control={control} lead={open("orders") && view.drafts?.order ? <OrderDraft view={view} busy={busy} signOrders={signOrders} /> : null}>
        {inside.map((key) => blocks(pick.now.action?.kind === "step")[key])}
        <ActionBar actions={quietActions(state, "doctor")} isOpen={open} onToggle={toggle} />
      </NowCard>
      {afterNow}
      {open("orders") && <OrdersDictation view={view} busy={busy} upload={upload} ask={ask} signOrders={signOrders} />}
      {open("photo") && <PhotoCard title={state === "ward" ? "Wound photo" : "Reference photo"} busy={busy} upload={upload} />}
      {below.map((key) => <section className="card" key={key} aria-label={BLOCK_TITLE[key]}><p className="label">{BLOCK_TITLE[key]}</p>{blocks(false)[key]}</section>)}
      <Clinic view={view} busy={busy} act={act} upload={upload} />
      <Theatre view={view} busy={busy} act={act} upload={upload} ask={ask} nowMs={nowMs} />
    </>
  );
}

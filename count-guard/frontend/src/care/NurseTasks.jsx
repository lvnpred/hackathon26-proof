import { useState } from "react";
import Dictate from "./Dictate";
import ObsForm from "./ObsForm";
import Opens from "./Opens.jsx";
import AiMoment from "./AiMoment.jsx";
import Provenance from "./Provenance.jsx";
import TaskProof from "./TaskProof";
import VideoCheck from "./VideoCheck";
import { heardHow } from "./askText";
import { doneBody, lastDoneLine, rowForm, rowSession, voiceTarget } from "./drafts";
import Source from "./Source.jsx";
import { FROM_VOICE, isPrepared } from "./source.js";
import { rowMark, taskGroups } from "./tasklist";
import { momentFor } from "./moments.js";
import { latestCheck, taskVideoLabel } from "./video";
import { own } from "./stepOutcome.js";
import { ExpandButton } from "./ModelExpand.jsx";

function TaskRow({ view, row, by, busy, act, upload, ask, micOpen, onMic, onProof, onSession, onSaved }) {
  const { task, due, status } = row;
  // The row's spoken completion until it is saved: its values fill this row's form (clarity §4.5).
  const [said, setSaid] = useState(null);
  const [filled, setFilled] = useState(0); // bumps when spoken values fill the form, so ObsForm shows them
  const [error, setError] = useState("");
  const clear = () => { setSaid(null); setFilled((n) => n + 1); };
  async function done(body = {}) {
    const out = said
      ? doneBody({ task, via: said.via, transcript: said.transcript, form: rowForm(body.values), heardBy: said.heardBy,
        proposed: said.proposal.values, edited: said.edited, heardText: said.heardText })
      : { body };
    if (out.error) return setError(out.error);
    setError("");
    const next = await act(`/tasks/${task.id}/done`, { by, via: "tap", note: "", ...out.body });
    if (next && said) { setSaid(null); onSaved(); }
    return next;
  }
  const mark = rowMark(task, due);
  const live = due !== "paused";
  const last = lastDoneLine(task, view.photos);
  const proofMoment = momentFor(view, last?.evidenceId);
  // The last save was from what was heard: the same predicate as the server's acts (acts.py), so the mark has an act.
  const lastAt = (task.done || []).slice(-1)[0]?.at_ms;
  const heardAct = (view.acts || []).find((a) => a.type === "task.done" && a.ref === task.id && a.at_ms === lastAt);
  const heardLast = Boolean(heardAct);
  const video = task.proof === "video" && task.has_setup;

  // The proposal comes back with its evidence, so the Dictate step says how Spark did; `o` is that step's opts.
  const send = async ({ text, heard }, o) => {
    const how = heardHow(heard?.text, text, heard?.by); // edited heard words stay heard (clarity §4.3)
    const proposal = await ask("/dictate/task", undefined, { text, by, heard_by: how.heard_by }, "/dictate/task", own(o));
    if (!proposal) return null;
    const session = { ...rowSession(proposal, task), edited: Boolean(how.edited), heardText: how.heard_text || "" };
    if (voiceTarget(task) === "proof") onSession(session, task); // Confirm task is for photo proofs only
    else { setSaid(session); setFilled((n) => n + 1); }
    return proposal;
  };

  return (
    <li className="task-row" data-task={task.id}>
      <div className="row between">
        <span>{task.title}</span>
        <span className={`pill ${due === "overdue" ? "sun" : "info"}`}>{status}</span>
        {live && (
          <button type="button" className="mic-button" aria-label={`Say it: ${task.title}`} aria-expanded={micOpen} disabled={busy} onClick={onMic}>🎙</button>
        )}
      </div>
      {last && (
        <p className="small muted">
          {last.text}
          {last.match && <> · <span className={`pill ${last.flagged ? "sun" : "info"}`}>{last.match}</span></>}
          {heardLast && <> <Provenance item={{ id: task.id }} events={view.acts} /> <ExpandButton record={{ eventId: heardAct.id, ref: task.id }} view={view} title={`Said: ${task.title}`} /></>}
        </p>
      )}
      {proofMoment && <AiMoment moment={proofMoment} role="nurse" episodeId={view.episode?.id} />}
      {micOpen && live && (
        <Dictate
          bare
          label={`Say it: ${task.title}`}
          verb={task.kind === "obs" ? "Fill the form" : "Use this"}
          autoSend
          busy={busy}
          sendCapability="wording"
          view={view}
          onHear={(file, o) => ask("/ask/hear", file, { by }, "/dictate/task", own(o))}
          onSend={send}
        />
      )}
      {said && (
        <p className="small" role="status">
          “{said.transcript}” <Source words={said.via === "voice" ? FROM_VOICE : null} prepared={said.via === "voice" && isPrepared({ heard_by: said.heardBy })} />
          {/* Heard values stay the AI's proposal until the nurse saves them (then the row reads Accepted or Changed by). */}
          {said.via === "voice" && <> <Provenance item={{ id: task.id, ai: said.ai === true }} events={[]} /></>}
          {" "}{task.kind === "obs" ? "Check the values, then save." : `Saved when you press ${task.mode === "start_end" ? "End" : mark.label}.`}
          {" "}<button type="button" className="quiet" disabled={busy} onClick={clear}>Clear</button>
        </p>
      )}
      {error && <p className="error small" role="alert">{error}</p>}
      {live && task.proof === "photo" && <button type="button" disabled={busy} onClick={() => onProof(task)}>Add photo proof</button>}
      {taskVideoLabel(task) && !video && <p className="small muted">{taskVideoLabel(task)}</p>}
      {live && video && (
        <VideoCheck
          title="Set-up check"
          kind="setup"
          episodeId={view.episode?.id}
          version={view.timeline?.length}
          check={latestCheck(view, "setup", task.id)}
          moment={momentFor(view, latestCheck(view, "setup", task.id)?.id)}
          busy={busy}
          onFile={(file, o) => upload("/video", file, { check: "setup", task_id: task.id, by }, undefined, own(o))}
        />
      )}
      {live && task.kind === "obs" && <button type="button" className="quiet" disabled={busy} onClick={() => onProof(task)}>Read from monitor photo</button>}
      {live && task.kind === "obs" && <ObsForm key={`${task.id}:${filled}`} busy={busy} due={due} label={mark.label} initial={said ? rowForm(said.proposal.values) : {}} onSave={(values) => done({ values })} />}
      {live && task.kind !== "obs" && task.mode === "start_end" && (
        task.status === "running"
          ? <button type="button" disabled={busy} onClick={() => done()}>End</button>
          : <button type="button" disabled={busy} onClick={() => act(`/tasks/${task.id}/begin`, { by })}>Begin</button>
      )}
      {live && task.kind !== "obs" && task.mode !== "start_end" && (
        <button type="button" disabled={busy} onClick={() => done()}>{mark.label}</button>
      )}
    </li>
  );
}

function Group({ title, empty, rows, micId, setMicId, ...rest }) {
  return (
    <>
      <p className="label">{title}</p>
      {rows.length === 0 && <p className="empty small">{empty}</p>}
      <ul className="task-list">
        {rows.map((row) => (
          <TaskRow
            key={row.task.id}
            row={row}
            micOpen={micId === row.task.id}
            onMic={() => setMicId(micId === row.task.id ? null : row.task.id)}
            onSaved={() => setMicId((open) => (open === row.task.id ? null : open))}
            {...rest}
          />
        ))}
      </ul>
    </>
  );
}

// The nurse's one task list. A mic on each row opens a Dictate there: what is heard fills that row (its ObsForm, or its
// own button for a tick task) in one step, and the nurse saves. Confirm task is only for photo proofs (clarity §4.5).
// Outside an admitted state the list stays, its buttons disabled, and says when it opens (clarity §4.4).
export default function NurseTasks({ view, nowMs, state, by, busy: working, act, upload, ask, reason = "" }) {
  const busy = working || Boolean(reason);
  const [micId, setMicId] = useState(null);
  const [confirm, setConfirm] = useState(null); // { task, session }
  const groups = taskGroups(view.tasks || [], nowMs, state);
  const close = () => { setConfirm(null); setMicId(null); };
  const rest = {
    view, by, busy, act, upload, ask,
    onProof: (task) => setConfirm({ task, session: { via: "tap", transcript: "", proposal: { candidates: [task], values: {} } } }),
    onSession: (session, task) => { setMicId(null); setConfirm({ task, session }); },
  };
  return (
    <>
      {confirm && <TaskProof key={`${confirm.task.id}:${confirm.session.transcript}`} view={view} task={confirm.task} session={confirm.session} by={by} busy={busy} act={act} upload={upload} onClear={close} />}
      <section className="card" aria-label="Tasks">
        <Opens reason={reason} />
        <Group title="Due now" empty="Nothing due now." rows={groups.now} micId={micId} setMicId={setMicId} {...rest} />
        <Group title="Later today" empty="Nothing later today." rows={groups.later} micId={micId} setMicId={setMicId} {...rest} />
      </section>
    </>
  );
}

import { useState } from "react";
import Dictate from "./Dictate";
import ObsForm from "./ObsForm";
import TaskProof from "./TaskProof";
import VideoCheck from "./VideoCheck";
import { answerHow } from "./askText";
import { lastDoneLine, rowSession } from "./drafts";
import { rowMark, taskGroups } from "./tasklist";
import { latestCheck, taskVideoLabel } from "./video";

function TaskRow({ view, row, by, busy, act, upload, ask, micOpen, onMic, onProof, onSession }) {
  const { task, due, status } = row;
  const done = (body = {}) => act(`/tasks/${task.id}/done`, { by, via: "tap", note: "", ...body });
  const mark = rowMark(task, due);
  const live = due !== "paused";
  const last = lastDoneLine(task, view.photos);
  const video = task.proof === "video" && task.has_setup;

  const send = async ({ text, heard }) => {
    const proposal = await ask("/dictate/task", undefined, { text, by, heard_by: answerHow(heard?.text, text, heard?.by).heard_by });
    if (!proposal) return false;
    onSession(rowSession(proposal, task), task);
    return true;
  };

  return (
    <li className="task-row">
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
        </p>
      )}
      {micOpen && live && (
        <Dictate
          bare
          label={`Say it: ${task.title}`}
          verb="Use this"
          busy={busy}
          onHear={(file) => ask("/ask/hear", file, { by }, "/dictate/task")}
          onSend={send}
        />
      )}
      {live && task.proof === "photo" && <button type="button" disabled={busy} onClick={() => onProof(task)}>Add photo proof</button>}
      {taskVideoLabel(task) && !video && <p className="small muted">{taskVideoLabel(task)}</p>}
      {live && video && (
        <VideoCheck
          title="Set-up check"
          kind="setup"
          check={latestCheck(view, "setup", task.id)}
          busy={busy}
          onFile={(file) => upload("/video", file, { check: "setup", task_id: task.id, by })}
        />
      )}
      {live && task.kind === "obs" && <ObsForm busy={busy} due={due} label={mark.label} primary={mark.primary} onSave={(values) => done({ values })} />}
      {live && task.kind !== "obs" && task.mode === "start_end" && (
        task.status === "running"
          ? <button type="button" className="primary" disabled={busy} onClick={() => done()}>End</button>
          : <button type="button" disabled={busy} onClick={() => act(`/tasks/${task.id}/begin`, { by })}>Begin</button>
      )}
      {live && task.kind !== "obs" && task.mode !== "start_end" && (
        <button type="button" className={mark.primary ? "primary" : undefined} disabled={busy} onClick={() => done()}>{mark.label}</button>
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
            {...rest}
          />
        ))}
      </ul>
    </>
  );
}

// The nurse's one task list. A mic on each row opens a Dictate there; Confirm task is the one panel for all rows.
export default function NurseTasks({ view, nowMs, state, by, busy, act, upload, ask }) {
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
        <Group title="Due now" empty="Nothing due now." rows={groups.now} micId={micId} setMicId={setMicId} {...rest} />
        <Group title="Later today" empty="Nothing later today." rows={groups.later} micId={micId} setMicId={setMicId} {...rest} />
      </section>
    </>
  );
}

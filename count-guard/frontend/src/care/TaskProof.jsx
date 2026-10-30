import { useEffect, useState } from "react";
import { answerHow } from "./askText";
import Dictate from "./Dictate";
import ObsForm from "./ObsForm";
import { doneBody, MATCH_LABEL, newestPhoto, proposalChoices, sourceLabel } from "./drafts";
import { obsValues } from "./tasklist";

const strings = (values) => Object.fromEntries(Object.entries(values || {}).map(([k, v]) => [k, String(v)]));

// A nurse completes a task: say it, pick the task, check the values, add a photo, press Confirm.
// Nothing is saved until Confirm. A photo that does not match is flagged and Confirm stays on (D9).
export default function TaskProof({ view, tasks, by, busy, act, upload, ask, preset, onClear }) {
  const [session, setSession] = useState(null); // { proposal, via, transcript, source, heardBy }
  const [pickId, setPickId] = useState("");
  const [form, setForm] = useState({});
  const [photo, setPhoto] = useState(null);
  const [error, setError] = useState("");

  const open = (next, id, values) => {
    setSession(next);
    setPickId(id);
    setForm(strings(values));
    setPhoto(null);
    setError("");
  };
  const clear = () => {
    setSession(null);
    setPickId("");
    setForm({});
    setPhoto(null);
    setError("");
    onClear?.();
  };

  // "Add photo proof" opens the card on that task: tapped, nothing said.
  useEffect(() => {
    if (preset) open({ proposal: { candidates: [preset], values: {} }, via: "tap", transcript: "", source: null }, preset.id, {});
  }, [preset]);

  const hear = (file) => ask("/ask/hear", file, { by }, "/dictate/task");

  async function listen({ text, heard }) {
    const proposal = await ask("/dictate/task", undefined, { text, by, heard_by: answerHow(heard?.text, text, heard?.by).heard_by });
    if (!proposal) return false;
    const { choices, pick } = proposalChoices(proposal, tasks);
    open(
      { proposal, via: proposal.heard_by === "typed" ? "text" : "voice", transcript: proposal.transcript || "", source: proposal.source, heardBy: proposal.heard_by },
      pick ? "" : choices[0].id,
      proposal.values,
    );
    return true;
  }

  if (!session) return <Dictate label="Complete a task by voice" verb="Use this" busy={busy} onHear={hear} onSend={listen} />;

  const { choices, pick } = proposalChoices(session.proposal, tasks);
  const task = tasks.find((t) => t.id === pickId) || choices.find((c) => c.id === pickId) || null;

  async function addPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !task) return;
    const stated = task.kind === "obs" ? obsValues(form).values || {} : {};
    const next = await upload("/photos", file, { purpose: "proof", task_id: task.id, by, sbp: stated.sbp, dbp: stated.dbp, hr: stated.hr });
    if (next) setPhoto(newestPhoto(next, task.id));
  }

  async function confirm() {
    if (task.mode === "start_end" && task.status !== "running") {
      if (await act(`/tasks/${task.id}/begin`, { by })) clear();
      return;
    }
    const out = doneBody({ task, via: session.via, transcript: session.transcript, form, photo });
    if (out.error) return setError(out.error);
    setError("");
    if (await act(`/tasks/${task.id}/done`, { by, ...out.body })) clear();
  }

  return (
    <section className="card" aria-label="Complete a task by voice">
      <p className="label">Complete a task by voice</p>
      {session.transcript && (
        <p className="small">
          “{session.transcript}” <span className="muted">· {sourceLabel(session.source)}</span>
          {session.heardBy && <span className="muted"> · Heard by: {sourceLabel(session.heardBy)}</span>}
        </p>
      )}
      {pick && choices.length === 0 && <p className="empty small">No open tasks.</p>}
      {choices.length > 0 && (
        <div role="radiogroup" aria-label="Which task">
          {choices.map((choice) => (
            <label className="field" key={choice.id}>
              <input
                type="radio"
                name="task-proof"
                checked={choice.id === pickId}
                onChange={() => { setPickId(choice.id); setPhoto(null); setError(""); }}
              />{" "}
              {choice.title}
            </label>
          ))}
        </div>
      )}
      {task?.kind === "obs" && (
        <ObsForm key={task.id} busy={busy} initial={form} onChange={setForm} />
      )}
      {task && (
        <label className="field">
          Add photo
          <input type="file" accept="image/*" capture="environment" disabled={busy} onChange={addPhoto} />
        </label>
      )}
      {photo && (
        <p className="small">
          <span className={`pill ${photo.check?.match === "mismatch" ? "sun" : "info"}`}>{MATCH_LABEL[photo.check?.match] || MATCH_LABEL.none}</span>{" "}
          <span className="muted">({sourceLabel(photo.check?.source)})</span>{" "}
          {photo.check?.why}
        </p>
      )}
      {error && <p className="error small" role="alert">{error}</p>}
      <div className="row">
        <button type="button" className="primary" disabled={busy || !task} onClick={confirm}>Confirm</button>
        <button type="button" disabled={busy} onClick={clear}>Cancel</button>
      </div>
    </section>
  );
}

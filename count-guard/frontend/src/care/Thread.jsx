import { ASK_DOCTOR, NOT_FOUND, answerByLine, medicineLine } from "./askText.js";
import { Evidence } from "./Evidence.jsx";
import { sourceLabel } from "./drafts";
import { threadItems, threadStatus } from "./thread.js";

const THUMB = { objectFit: "cover", borderRadius: 6 };

function Answer({ item, onAskDoctor, episodeId }) {
  const { kind, answer, raw } = item;
  if (kind === "record" && answer) {
    return (
      <>
        <p>{answer.text || NOT_FOUND}</p>
        {answer.found && <ul>{(answer.sources || []).map((line) => <li key={line.id}><q>{line.text}</q></li>)}</ul>}
        <p className="small muted">{answerByLine(answer)}</p>
        {!answer.found && <button onClick={() => onAskDoctor(item.said)}>{ASK_DOCTOR}</button>}
      </>
    );
  }
  if (kind === "doctor" && answer) {
    return (
      <>
        <p>{answer.text}</p>
        <p className="small muted">{answerByLine(answer)}</p>
      </>
    );
  }
  if (kind === "photo") {
    return (
      <>
        <img src={raw.photo.url} alt="Your healing photo" width={96} height={96} style={THUMB} />
        {answer && <p>{answer.label}{answer.note && <> · {answer.note}</>} <span className="small muted">{answer.by}</span></p>}
      </>
    );
  }
  if (kind === "medicines") {
    return (
      <>
        <img src={raw.photo.url} alt="Your medicines photo" width={96} height={96} style={THUMB} />
        <ul className="task-list">
          {raw.rows.map((row, i) => <li key={i}><span className={row.flag ? "pill sun" : ""}>{medicineLine(row)}</span></li>)}
        </ul>
        <p className="small">{raw.why} <span className="muted">({sourceLabel(raw.source)})</span></p>
        {raw.evidence_id && <Evidence episodeId={episodeId} evidenceId={raw.evidence_id} linkLines={false} />}
      </>
    );
  }
  return null;
}

// Everything the patient sent, newest first, each with its status and answer.
export default function Thread({ view, nowMs, onAskDoctor }) {
  const items = threadItems(view);
  return (
    <section className="card" aria-label="My messages">
      <p className="label">My messages</p>
      {items.length === 0 ? (
        <p className="empty small">Nothing sent yet. Ask your record or Dr. Rao above.</p>
      ) : (
        <ul className="thread">
          {items.map((item) => (
            <li className="thread-row" data-line={item.id} key={item.id}>
              <p className="small"><b>{item.title}</b> <span className="pill">{threadStatus(item, nowMs)}</span></p>
              {item.said && <p className="quote">{"“"}{item.said}{"”"}</p>}
              <Answer item={item} onAskDoctor={onAskDoctor} episodeId={view.episode?.id} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

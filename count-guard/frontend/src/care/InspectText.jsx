import { useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useEvidence } from "./Evidence.jsx";
import { NOT_FOUND, questionText } from "./askText.js";
import { cropStyle } from "./brownbag.js";
import { SPARK_WORDING, chartLine, draftSources, recordLine, ruleCards } from "./inspect.js";

const NO_SOURCES = "No record lines were cited.";
const NO_INPUT = "No input: this check compares two records.";

// A staff reader jumps to the chart line; a patient reads the quote.
function LineLink({ line, episodeId, lens }) {
  const text = recordLine(line, lens);
  if (lens === "patient" || !episodeId) return <q>{text}</q>;
  return <Link to={chartLine(episodeId, line.id)}>{text}</Link>;
}

// The question as the role may read it: the patient sees their own words.
export function AnswerInput({ moment, role, lens }) {
  const refs = moment.refs || {};
  const shown = questionText(lens === "patient" ? "doctor" : role, { text: refs.question });
  return <div className="inspector-input"><p className="quote">{"“"}{shown}{"”"}</p></div>;
}

// The answer, then each cited line: a button into the chart (staff) or a quote (patient).
export function AnswerFound({ moment, episodeId, lens }) {
  const navigate = useNavigate();
  const refs = moment.refs || {};
  const sources = refs.sources || [];
  return (
    <div className="inspector-found">
      <p>{refs.answer || NOT_FOUND}</p>
      {refs.found && (sources.length ? (
        <ul>
          {sources.map((s) => (
            <li key={s.id}>
              {lens === "patient" || !episodeId
                ? <q>{s.text}</q>
                : <button type="button" className="quiet" onClick={() => navigate(chartLine(episodeId, s.id))}>{s.text || s.id}</button>}
            </li>
          ))}
        </ul>
      ) : <p className="muted small">{NO_SOURCES}</p>)}
    </div>
  );
}

export function RuleInput() {
  return <div className="inspector-input"><p className="muted">{NO_INPUT}</p></div>;
}

// Ordered / prescribed beside Recorded / read, then the rule in words.
export function RuleFound({ moment, lens }) {
  const refs = moment.refs || {};
  return (
    <div className="inspector-found">
      <div className="rule-cards">
        {ruleCards(refs, lens).map((c) => (
          <div key={c.heading} className="card">
            <p className="label">{c.heading}</p>
            <p>{c.line}</p>
          </div>
        ))}
      </div>
      {refs.rule && <p className="small">{`Rule: ${refs.rule}`}</p>}
    </div>
  );
}

// The record lines the draft was written from.
export function DraftInput({ moment, episodeId, lens }) {
  const lines = draftSources(moment.refs);
  if (!lines.length) return <div className="inspector-input"><p className="muted">{NO_SOURCES}</p></div>;
  return (
    <ul className="inspector-input">
      {lines.map((line) => <li key={line.id}><LineLink line={line} episodeId={episodeId} lens={lens} /></li>)}
    </ul>
  );
}

function Evidence({ lines, episodeId, lens }) {
  if (!lines?.length) return null;
  return (
    <ul className="small">
      {lines.map((line) => <li key={line.id}><LineLink line={line} episodeId={episodeId} lens={lens} /></li>)}
    </ul>
  );
}

// Day plan rows: the crop from the medicines photo; the focused row is lit and scrolled into view.
function PlanRows({ moment, episodeId, focus, setFocus }) {
  const { data } = useEvidence(episodeId, moment.evidence_id, !moment.evidence_id);
  const { rows = [], photo_id: photoId } = moment.refs || {};
  const regions = data?.regions || moment.refs?.regions || [];
  const url = photoId ? `/journey/episodes/${episodeId}/photos/${photoId}` : "";
  const lit = useRef(null);
  useEffect(() => { lit.current?.scrollIntoView?.({ block: "nearest" }); }, [focus]);
  return (
    <ul className="stack">
      {rows.map((row, i) => {
        const on = focus === row.key;
        const bbox = row.region == null ? null : regions[row.region]?.bbox;
        return (
          <li key={`${row.key}-${i}`} ref={on ? lit : null} className={`plan-item${on ? " lit" : ""}`} data-row={row.key}>
            {bbox && url && <span className="crop" style={cropStyle(bbox, url)} aria-hidden="true" />}
            <button type="button" className="quiet" aria-pressed={on} onClick={() => setFocus(on ? null : row.key)}>
              <b>{row.medicine}</b> <span className="small">{row.text}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// Handover: the model text (Spark only), then each line with its evidence. Day plan: rows. Card: its lines.
export function DraftFound({ moment, episodeId, lens, focus, setFocus }) {
  const refs = moment.refs || {};
  if (moment.capability === "day_plan") {
    return <div className="inspector-found"><PlanRows moment={moment} episodeId={episodeId} focus={focus} setFocus={setFocus} /></div>;
  }
  if (moment.capability === "discharge_card") {
    return <div className="inspector-found">{(refs.lines || []).map((l) => <p key={l.text}>{l.text}</p>)}</div>;
  }
  return (
    <div className="inspector-found">
      {refs.wording === SPARK_WORDING && refs.text && <p className="quote">{refs.text}</p>}
      <ul>
        {(refs.lines || []).map((l, i) => (
          <li key={i}>
            <p>{l.text}</p>
            <Evidence lines={l.evidence} episodeId={episodeId} lens={lens} />
          </li>
        ))}
      </ul>
    </div>
  );
}

import Correct from "./Correct.jsx";
import Dictate from "./Dictate.jsx";
import Provenance from "./Provenance.jsx";
import { madeByModel } from "./provenance.js";
import { heardHow } from "./askText.js";
import Source from "./Source.jsx";
import { FROM_VOICE, isPrepared } from "./source.js";
import { own } from "./stepOutcome.js";
import { drugLine, drugStatus, heardPackLine } from "./theatreLive.js";
import { ExpandButton } from "./ModelExpand.jsx";

// Drug given by voice (spec §6.4): say or type the line, check the heard row, then a person taps to confirm.
// A pack line ("opening twenty swabs") is only heard here: the swab count changes when a person confirms the pack.
// Hearing goes through ward.ask with the Dictate box's voice step, so its upload, checking and any failure show there.
export default function TheatreDrugs({ episodeId, panel, by, busy, act, upload, ask, acts = [] }) {
  const hear = (file, o) => ask("/ask/hear", file, { by }, "/theatre/drug", own(o));
  // Heard words the person edited stay heard, with the words as heard, so the confirmed row can read "Changed by".
  const send = ({ text, heard }) => {
    const how = heardHow(heard?.text, text, heard?.by);
    return upload("/theatre/drug", null, { text, by, heard_by: how.heard_by, ...(how.edited ? { heard_text: how.heard_text } : {}) }, "/theatre/drug");
  };
  const open = panel.packs.filter((pack) => !pack.confirmed_by);
  const view = { episode: { id: episodeId }, acts }; // what the Expand view needs: the episode and the person acts
  return (
    <section className="card" aria-label="Drug given">
      <Dictate bare label="Drug given" field="Drug, strength, amount, route" verb="Add heard line" capability="task_voice"
        placeholder="e.g. lignocaine two percent, five ml, local infiltration" maxLength={400} busy={busy} view={view} onHear={hear} onSend={send} />
      {panel.drugs.length > 0 && (
        <ul className="plain-list">
          {panel.drugs.map((row) => (
            <li key={row.id}>
              <strong>{drugLine(row)}</strong>{" "}
              {row.source !== "typed" && <Source words={FROM_VOICE} prepared={isPrepared(row)} />}
              {/* Who confirmed shows on every confirmed row; only a heard row was the AI's proposal. */}
              <Provenance item={{ id: row.id, at_ms: row.at_ms, ai: row.source !== "typed" && madeByModel(row) }} events={acts} />{" "}
              <ExpandButton record={{ eventId: row.id }} view={view} title={`Heard: ${drugLine(row)}`} />
              <p className="small muted">{drugStatus(row)}</p>
              {!row.given && (
                <button type="button" disabled={busy} onClick={() => act(`/theatre/drug/${row.id}/confirm`, { by })}>
                  Confirm given
                </button>
              )}
              <Correct written={row.given ? { event_id: row.given.id, type: "drug.given" } : { event_id: row.id, type: "druglog.parsed" }}
                by={by} episodeId={episodeId} act={act} busy={busy} />
            </li>
          ))}
        </ul>
      )}
      {panel.packs.length > 0 && (
        <ul className="plain-list">
          {panel.packs.map((pack) => (
            <li key={pack.id}>
              <span className="small">{heardPackLine(pack)}</span>{" "}
              {pack.source !== "typed" && <Source words={FROM_VOICE} prepared={isPrepared(pack)} />}
              <Provenance item={{ id: pack.id, at_ms: pack.at_ms, ai: pack.source !== "typed" && madeByModel(pack) }} events={acts} />{" "}
              <ExpandButton record={{ eventId: pack.id }} view={view} title="Heard pack" />
              {!pack.confirmed_by && (
                <button type="button" disabled={busy} onClick={() => act(`/theatre/pack/${pack.id}/confirm`, { by })}>
                  Confirm pack of {pack.n}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {open.length > 0 && <p className="small muted">A heard pack is not in the swab count until a person confirms it.</p>}
    </section>
  );
}

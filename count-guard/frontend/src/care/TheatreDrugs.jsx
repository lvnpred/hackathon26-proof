import { useState } from "react";
import Dictate from "./Dictate.jsx";
import Source from "./Source.jsx";
import { FROM_VOICE, isPrepared } from "./source.js";
import { uploadJourney } from "../journey.js";
import { drugLine, drugStatus, heardPackLine } from "./theatreLive.js";

// Drug given by voice (spec §6.4): say or type the line, check the heard row, then a person taps to confirm.
// A pack line ("opening twenty swabs") is only heard here: the swab count changes when a person confirms the pack.
export default function TheatreDrugs({ episodeId, panel, by, busy, act, upload }) {
  const [problem, setProblem] = useState("");
  async function hear(file) {
    setProblem("");
    try {
      return await uploadJourney(episodeId, "/ask/hear", file, { by });
    } catch (exc) {
      setProblem(exc.message);
      return null;
    }
  }
  const send = ({ text, heard }) =>
    upload("/theatre/drug", null, { text, by, heard_by: heard && heard.text === text ? heard.by : "" }, "/theatre/drug");
  const open = panel.packs.filter((pack) => !pack.confirmed_by);
  return (
    <section className="card" aria-label="Drug given">
      <Dictate bare label="Drug given" field="Drug, strength, amount, route" verb="Add heard line" capability="task_voice"
        placeholder="e.g. lignocaine two percent, five ml, local infiltration" maxLength={400} busy={busy} onHear={hear} onSend={send} />
      {problem && <p className="note small" role="alert">{problem}</p>}
      {panel.drugs.length > 0 && (
        <ul className="plain-list">
          {panel.drugs.map((row) => (
            <li key={row.id}>
              <strong>{drugLine(row)}</strong>{" "}
              {row.source !== "typed" && <Source words={FROM_VOICE} prepared={isPrepared(row)} />}
              <p className="small muted">{drugStatus(row)}</p>
              {!row.given && (
                <button type="button" disabled={busy} onClick={() => act(`/theatre/drug/${row.id}/confirm`, { by })}>
                  Confirm given
                </button>
              )}
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

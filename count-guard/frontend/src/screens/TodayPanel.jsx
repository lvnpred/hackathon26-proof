import { useState } from "react";
import { parseStrips } from "../journey";
import Fault from "../care/Fault";

const SLOTS = [
  ["morning", "Morning"],
  ["afternoon", "Afternoon"],
  ["night", "Night"],
];

export function Medicines({ schedule }) {
  const daily = schedule.filter((row) => row.slots && !row.as_needed);
  const needed = schedule.filter((row) => row.as_needed || !row.slots);
  if (schedule.length === 0) return <p className="empty small">Your medicines appear here once the doctor's prescription is in.</p>;
  return (
    <div className="stack">
      {daily.length > 0 && (
        <div className="table-box">
          <table>
            <thead>
              <tr><th>Medicine</th>{SLOTS.map(([key, label]) => <th key={key}>{label}</th>)}</tr>
            </thead>
            <tbody>
              {daily.map((row, index) => (
                <tr key={`${row.key}-${index}`}>
                  <td>
                    <b>{row.medicine}</b>
                    <div className="small muted">
                      {[row.timing, row.days ? `${row.days} days` : "", row.note].filter(Boolean).join(" · ")}
                    </div>
                  </td>
                  {SLOTS.map(([key]) => <td key={key} className="num">{row.slots[key] || ""}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {needed.length > 0 && (
        <div className="stack">
          <p><b>When needed</b></p>
          {needed.map((row, index) => (
            <p key={`${row.key}-${index}`} className="small">
              {row.medicine}
              {[row.timing, row.days ? `${row.days} days` : "", row.note].filter(Boolean).map((part) => ` · ${part}`).join("")}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

// "For you now": the nudges addressed to the patient.
export function Nudges({ view, busy, act, fault, episodeId }) {
  const mine = (view?.nudges || []).filter((nudge) => nudge.to === "patient");
  if (mine.length === 0) return null;
  return (
    <section className="card" style={{ borderColor: "var(--sun)", background: "var(--sun-soft)" }}>
      <p className="label sun">For you now</p>
      {mine.map((nudge) => (
        <div className="stack" key={nudge.id}>
          <p><b>{nudge.says}</b></p>
          <div className="row between">
            <span className="small muted">{nudge.when}</span>
            <button className="primary" disabled={busy} onClick={() => act(`/nudges/${nudge.id}/seen`, { by: "patient", note: "Done." })}>
              I've done this
            </button>
          </div>
        </div>
      ))}
      <Fault fault={fault} episodeId={episodeId} only={["/nudges/"]} />
    </section>
  );
}

// The calendar reminders button, its download link and its fault.
export function Reminders({ view, busy, act, fault, episodeId }) {
  const [added, setIcs] = useState("");
  const ics = added || view?.ics_url || "";

  async function reminders() {
    const next = await act("/reminders", {});
    if (next?.ics_url) setIcs(next.ics_url);
  }

  return (
    <>
      <button onClick={reminders} disabled={busy || !view?.rx}>Add reminders to my calendar</button>
      {ics && <a href={ics} download>Download the calendar file</a>}
      <Fault fault={fault} episodeId={episodeId} only={["/reminders"]} />
    </>
  );
}

// Type or photograph the strips at home. upload(path, file) resolves to the new view, or null.
export function Strips({ view, busy, act, upload, fault, episodeId }) {
  const [lines, setLines] = useState("amlodipine 10 mg");
  const [photoNote, setPhotoNote] = useState("");
  const strips = view?.strips || [];

  async function photo(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !view) return;
    setPhotoNote("");
    try {
      if (await upload("/strips/photo", file)) setPhotoNote("Photo read. Check the names below.");
    } catch (exc) {
      setPhotoNote(exc.message);
    }
  }

  return (
    <div className="stack">
      <p className="small muted">Type the strips you have at home, one per line: name then strength.</p>
      <label className="field">
        One strip per line
        <textarea rows={4} value={lines} onChange={(event) => setLines(event.target.value)} />
      </label>
      <button className="primary" disabled={busy || !lines.trim()} onClick={() => act("/strips", { strips: parseStrips(lines) })}>
        Check these strips
      </button>
      <label className="field">
        Photo of a strip
        <input type="file" accept="image/*" capture="environment" onChange={photo} disabled={busy} />
      </label>
      {photoNote && <p className="note" role="status">{photoNote}</p>}
      <Fault fault={fault} episodeId={episodeId} only={["/strips"]} />
      {strips.length > 0 && (
        <div className="rows">
          {strips.map((strip, index) => (
            <div className="list-row" key={`${strip.name_as_read}-${index}`}>
              <span>
                <b>{strip.generic || strip.name_as_read} {strip.strength}</b>
                <small>{strip.grounded ? strip.drug_class : "as read"} · {strip.source || strip.by}</small>
              </span>
              <span className={strip.grounded ? "tag ready" : "tag"}>{strip.grounded ? "known" : "as read"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

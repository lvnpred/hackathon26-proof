import { useState } from "react";
import Fault from "../care/Fault";

// The signed discharge card in plain words.
export function MyCard({ card }) {
  if (!card) return <p className="empty small">Your card appears here when the doctor signs it.</p>;
  return (
    <div className="stack">
      <h2>{card.title}</h2>
      <div className="stack">
        <p><b>Call if you notice</b></p>
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {card.warning_signs.map((sign) => <li key={sign}>{sign}</li>)}
        </ul>
      </div>
      {card.wound_care && <p><b>Wound:</b> {card.wound_care}</p>}
      {card.help_line && <p><b>Help line:</b> {card.help_line}</p>}
      {card.review && <p><b>Next visit:</b> {card.review}</p>}
      <p className="small muted">Signed by {card.by}</p>
    </div>
  );
}

// The "Need help" message box and button.
export function NeedHelp({ busy, act, fault, episodeId }) {
  const [says, setSays] = useState("");
  const [sent, setSent] = useState("");

  async function help() {
    const text = says.trim() || "I need help.";
    if (await act("/help", { says: text })) {
      setSays("");
      setSent("Your message is recorded for the ward. If it is an emergency, call the help line now.");
    }
  }

  return (
    <div className="stack">
      <label className="field">
        What is happening (optional)
        <input value={says} onChange={(event) => setSays(event.target.value)} placeholder="My wound is leaking" />
      </label>
      <button className="primary block" style={{ minHeight: 64, fontSize: 18 }} onClick={help} disabled={busy}>
        Need help
      </button>
      {sent && <p className="note" role="status">{sent}</p>}
      <Fault fault={fault} episodeId={episodeId} only={["/help"]} />
    </div>
  );
}

export function CheckIn({ card, busy, act, fault, episodeId }) {
  const [day, setDay] = useState("1");
  const [feels, setFeels] = useState("");
  const [note, setNote] = useState("");
  const [signs, setSigns] = useState([]);
  const [saved, setSaved] = useState("");

  function toggle(sign) {
    setSigns(signs.includes(sign) ? signs.filter((item) => item !== sign) : [...signs, sign]);
  }

  async function save() {
    const body = { day: Number(day), feels: feels.trim(), signs, note: note.trim() };
    if (await act("/checkin", body)) {
      setSaved(`Day ${day} check-in recorded.`);
      setFeels("");
      setNote("");
      setSigns([]);
    }
  }

  const dayNumber = Number(day);
  return (
    <section className="card">
      <p className="label">Day check-in</p>
      <div className="row">
        <label className="field" style={{ flex: "0 1 90px" }}>
          Day
          <input inputMode="numeric" value={day} onChange={(event) => setDay(event.target.value)} />
        </label>
        <label className="field" style={{ flex: "1 1 200px" }}>
          How do you feel?
          <input value={feels} onChange={(event) => setFeels(event.target.value)} placeholder="A bit sore, eating well" />
        </label>
      </div>
      {(card?.warning_signs || []).length > 0 && (
        <div className="stack" style={{ gap: 0 }}>
          <p className="small muted">Tick any you have now.</p>
          {card.warning_signs.map((sign) => (
            <label className="check" key={sign}>
              <input type="checkbox" checked={signs.includes(sign)} onChange={() => toggle(sign)} />
              {sign}
            </label>
          ))}
        </div>
      )}
      <label className="field">
        Anything else (optional)
        <input value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <button
        className="primary"
        onClick={save}
        disabled={busy || !feels.trim() || !Number.isInteger(dayNumber) || dayNumber < 1}
      >
        Send check-in
      </button>
      {saved && <p className="note" role="status">{saved}</p>}
      <Fault fault={fault} episodeId={episodeId} only={["/checkin"]} />
    </section>
  );
}

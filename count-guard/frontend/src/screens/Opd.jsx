import { useEffect, useState } from "react";
import { loadEpisode, send } from "../episode";
import { PageLead, Shell } from "../App";

export default function Opd() {
  const [view, setView] = useState(null);
  const [names, setNames] = useState("metoprolol 25 mg\namlodipine 5 mg");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadEpisode().then(setView).catch((exc) => setError(exc.message));
  }, []);

  async function saveText() {
    const body = JSON.stringify({
      text: JSON.stringify({
        strips: names
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean)
          .map((line) => {
            const match = line.match(/^(.+?)\s+(\d+\s*(?:mg|ml|g|mcg))$/i);
            return match ? { name: match[1], strength: match[2] } : { name: line, strength: "" };
          }),
      }),
    });
    const next = await send(`/morning/episodes/${view.episode.id}/brownbag/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    setView(next);
  }

  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file || !view) return;
    setError("");
    const data = new FormData();
    data.append("file", file);
    const response = await fetch(`/morning/episodes/${view.episode.id}/brownbag/photo`, {
      method: "POST",
      body: data,
    });
    const body = await response.json();
    setNote(body.detail || body.status);
  }

  const meds = view?.sheet?.opd || [];

  return (
    <Shell guide={view?.guide}>
      <PageLead
        kicker="Before the operation"
        title="Read the strips the person brought."
        body="One line per strip, name then strength. A name on the demo list is grounded and given a class. Any other name stays as read. A photo is kept on this computer. It is not sent to a model unless a key is set."
      />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <section className="main">
          <div className="card">
            <p className="label">Strips</p>
            <p className="small muted">Type one strip per line, or attach a photo. Without a Muse Spark key the photo stays on this machine and the names stay typed.</p>
            <label className="field">
              One strip per line
              <textarea rows={6} value={names} onChange={(event) => setNames(event.target.value)} />
            </label>
            <label className="field">
              Photo of the strips
              <input type="file" accept="image/*" onChange={upload} />
            </label>
            {note && <p className="note" role="status">{note}</p>}
            <div className="row">
              <button className="primary" onClick={saveText} disabled={!view}>Ground the list</button>
            </div>
          </div>
        </section>
        <aside className="side">
          <div className="card">
            <p className="label">Grounded</p>
            {meds.length === 0 && <p className="empty">Grounded names appear here after you ground the list.</p>}
            <div className="rows">
              {meds.map((item, index) => (
                <div className="list-row" key={`${item.generic}-${index}`}>
                  <span>
                    <b>{item.generic || item.name_as_read} {item.strength}</b>
                    {item.grounded && <small>{item.drug_class}</small>}
                  </span>
                  <span className={item.grounded ? "tag ready" : "tag"}>{item.grounded ? "grounded" : "as read"}</span>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </Shell>
  );
}

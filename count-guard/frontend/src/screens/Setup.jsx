import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ITEM_TYPES, PROP_ZONES, createCase, health, saveZones, uploadScenario } from "../api";
import { Models, PageLead, Pill, Shell } from "../App";

export default function Setup() {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [label, setLabel] = useState("Prop tray demo");
  const [picked, setPicked] = useState(["lap sponge", "gauze swab"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [caseId, setCaseId] = useState("");
  const [tool, setTool] = useState("tray");
  const [draft, setDraft] = useState([]);
  const [zones, setZones] = useState({ tray: [], field: [], bucket: [] });

  useEffect(() => {
    health().then(setStatus).catch(() => setStatus(null));
  }, []);

  async function playDemo() {
    setBusy(true);
    setError("");
    try {
      const created = await createCase("Prop tray demo", ITEM_TYPES);
      const snapshot = await uploadScenario(created.id, "demo");
      sessionStorage.setItem(`cg:${created.id}`, JSON.stringify(snapshot));
      navigate(`/case/${created.id}`);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  async function startBlank() {
    setBusy(true);
    setError("");
    try {
      const created = await createCase(label, picked);
      setCaseId(created.id);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  function addPoint(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Number(((event.clientX - rect.left) / rect.width).toFixed(4));
    const y = Number(((event.clientY - rect.top) / rect.height).toFixed(4));
    setDraft((points) => [...points, [x, y]]);
  }

  function closePolygon() {
    if (draft.length < 3) return;
    setZones((current) => ({ ...current, [tool]: draft }));
    setDraft([]);
  }

  async function save() {
    setError("");
    const payload = ["tray", "field", "bucket"].map((name) => ({ name, polygon: zones[name] }));
    if (payload.some((zone) => zone.polygon.length < 3)) {
      setError("Draw tray, field, and bucket. Each needs at least three points.");
      return;
    }
    await saveZones(caseId, payload);
    navigate(`/case/${caseId}`);
  }

  function usePropZones() {
    const next = {};
    for (const zone of PROP_ZONES) next[zone.name] = zone.polygon;
    setZones(next);
    setDraft([]);
  }

  const polygons = { ...zones, [tool]: draft.length ? draft : zones[tool] };

  return (
    <Shell subtitle="Camera count · separate from the morning" status={{ tone: "info", label: "Scripted demo" }}>
      <PageLead
        kicker="Camera count"
        title="This screen tracks swabs in a video."
        body="It is separate from the morning timeline. Play the closing-count demo to see one swab missing, with the last frame it was seen in. The model names below are the ones this screen can call. A missing key means that model is not called."
      />
      <Models health={status} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <section className="main">
          <div className="card hero">
            <p className="label">1. Setup</p>
            <h2>Play the closing-count demo</h2>
            <p>Draw the tray, the field, and the bucket once on the first frame. An item's normal path is tray, then field, then bucket.</p>
            <div className="row">
              {!caseId && (
                <button className="primary" disabled={busy} onClick={playDemo}>Play the closing-count demo</button>
              )}
              <span className="small muted">Scripted perception. SAM 3.1 is not called.</span>
            </div>
          </div>
        </section>
        <aside className="side">
          <div className="card">
            <p className="label">Or start a blank session</p>
            <label className="field">
              Session label
              <input value={label} onChange={(event) => setLabel(event.target.value)} />
            </label>
            <div className="rows">
              {ITEM_TYPES.map((item) => (
                <label className="check" key={item}>
                  <input
                    type="checkbox"
                    checked={picked.includes(item)}
                    onChange={() =>
                      setPicked((current) =>
                        current.includes(item) ? current.filter((name) => name !== item) : [...current, item],
                      )
                    }
                  />
                  {item}
                </label>
              ))}
            </div>
            <button disabled={busy || picked.length === 0} onClick={startBlank}>
              Start session
            </button>
          </div>
        </aside>
      </div>
      {caseId && (
        <section className="card">
          <p className="label">Zones for {caseId.slice(0, 8)}</p>
          <div className="row">
            {["tray", "field", "bucket"].map((name) => (
              <button key={name} aria-pressed={tool === name} onClick={() => { setTool(name); setDraft([]); }}>
                {tool === name ? `Drawing ${name}` : name}
                {zones[name].length >= 3 && <Pill tone="ready">ready</Pill>}
              </button>
            ))}
            <button onClick={closePolygon}>Close polygon</button>
            <button onClick={usePropZones}>Use prop-tray zones</button>
            <button className="primary" onClick={save}>Save zones</button>
          </div>
          <div className="draw">
            <svg viewBox="0 0 100 56" role="img" aria-label="Zone drawing surface" onClick={addPoint}>
              <rect width="100" height="56" fill="#f2ede3" />
              {Object.entries(polygons).map(([name, points]) =>
                points.length ? (
                  <polygon
                    key={name}
                    points={points.map(([x, y]) => `${x * 100},${y * 56}`).join(" ")}
                    fill={name === "tray" ? "#c2410c33" : name === "field" ? "#1d4ed833" : "#15803d33"}
                    stroke="#1c1915"
                  />
                ) : null,
              )}
            </svg>
          </div>
          <p className="small muted">Click to drop points for the {tool}. Close the polygon, then save all three.</p>
        </section>
      )}
    </Shell>
  );
}

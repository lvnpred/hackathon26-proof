import { useState } from "react";
import { num } from "../journey";

const DOSES = [
  { name: "Paracetamol", amount: "1 g IV", every_h: "6" },
  { name: "Ondansetron", amount: "4 mg IV", every_h: "8" },
];
const LIMITS = { sbp_min: "90", sbp_max: "160", hr_max: "110", spo2_min: "94", temp_max: "38" };
const LIMIT_LABELS = [
  ["sbp_min", "SBP low"],
  ["sbp_max", "SBP high"],
  ["hr_max", "HR max"],
  ["spo2_min", "SpO2 min"],
  ["temp_max", "Temp max °C"],
];

export function OrdersSummary({ orders }) {
  if (!orders) return <p className="empty small">No ward orders saved yet.</p>;
  const limits = orders.limits || {};
  return (
    <div className="stack">
      <div className="rows">
        {orders.doses.map((dose) => (
          <div className="list-row" key={dose.key || dose.name}>
            <span>
              <b>{dose.name} {dose.amount}</b>
              <small>every {dose.every_h} h</small>
            </span>
            <span className="tag">ordered</span>
          </div>
        ))}
      </div>
      <p className="small num">
        Observations every {orders.obs_every_h ?? "—"} h. SBP {limits.sbp_min ?? "—"}–{limits.sbp_max ?? "—"},
        HR max {limits.hr_max ?? "—"}, SpO2 min {limits.spo2_min ?? "—"}, temp max {limits.temp_max ?? "—"}.
      </p>
      <p className="small muted">Set by {orders.by}</p>
    </div>
  );
}

export default function DoctorOrders({ orders, busy, act }) {
  const [doses, setDoses] = useState(DOSES);
  const [obsEvery, setObsEvery] = useState("1");
  const [limits, setLimits] = useState(LIMITS);
  const [by, setBy] = useState("Dr. A. Rao (synthetic)");

  function editDose(index, field, value) {
    setDoses(doses.map((dose, at) => (at === index ? { ...dose, [field]: value } : dose)));
  }

  function save() {
    const limitBody = {};
    for (const [key] of LIMIT_LABELS) limitBody[key] = num(limits[key]);
    act("/orders", {
      doses: doses
        .filter((dose) => dose.name.trim())
        .map((dose) => ({ name: dose.name.trim(), amount: dose.amount.trim(), every_h: num(dose.every_h) })),
      obs_every_h: num(obsEvery),
      limits: limitBody,
      by: by.trim(),
    });
  }

  return (
    <section className="card">
      <p className="label">Ward orders and limits</p>
      <p className="small muted">The nurse sees these. A nudge fires when a logged dose or reading sits outside them.</p>
      {doses.map((dose, index) => (
        <div className="row" key={index}>
          <label className="field" style={{ flex: "2 1 140px" }}>
            Medicine
            <input value={dose.name} onChange={(event) => editDose(index, "name", event.target.value)} />
          </label>
          <label className="field" style={{ flex: "1 1 100px" }}>
            Amount
            <input value={dose.amount} onChange={(event) => editDose(index, "amount", event.target.value)} />
          </label>
          <label className="field" style={{ flex: "1 1 80px" }}>
            Every (h)
            <input inputMode="decimal" value={dose.every_h} onChange={(event) => editDose(index, "every_h", event.target.value)} />
          </label>
          <button className="quiet" onClick={() => setDoses(doses.filter((_, at) => at !== index))}>Remove</button>
        </div>
      ))}
      <button className="quiet" onClick={() => setDoses([...doses, { name: "", amount: "", every_h: "" }])}>Add a dose line</button>
      <div className="row">
        <label className="field" style={{ flex: "1 1 120px" }}>
          Observations every (h)
          <input inputMode="decimal" value={obsEvery} onChange={(event) => setObsEvery(event.target.value)} />
        </label>
        {LIMIT_LABELS.map(([key, label]) => (
          <label className="field" key={key} style={{ flex: "1 1 90px" }}>
            {label}
            <input inputMode="decimal" value={limits[key]} onChange={(event) => setLimits({ ...limits, [key]: event.target.value })} />
          </label>
        ))}
      </div>
      <div className="row">
        <label className="field" style={{ flex: "1 1 220px" }}>
          Ordered by
          <input value={by} onChange={(event) => setBy(event.target.value)} />
        </label>
        <button className="primary" onClick={save} disabled={busy || !by.trim()}>Save orders</button>
      </div>
      <div className="stack" style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
        <p className="label">Saved orders</p>
        <OrdersSummary orders={orders} />
      </div>
    </section>
  );
}

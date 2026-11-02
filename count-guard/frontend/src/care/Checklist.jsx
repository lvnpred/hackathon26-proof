import { useState } from "react";

// Every box must be ticked before the button enables. onDone gets { key: true, ... }.
// proof(key, label), when given, renders that item's photo check under it (spec §6.6).
export default function Checklist({ items, busy, onDone, button, primary = false, proof = null }) {
  const [ticked, setTicked] = useState({});
  const all = items.every(([key]) => ticked[key]);
  return (
    <div>
      <ul className="task-list">
        {items.map(([key, label]) => (
          <li key={key}>
            <label>
              <input
                type="checkbox"
                checked={Boolean(ticked[key])}
                onChange={(event) => setTicked({ ...ticked, [key]: event.target.checked })}
              />{" "}
              {label}
            </label>
            {proof && proof(key, label)}
          </li>
        ))}
      </ul>
      <button type="button" className={primary ? "primary" : undefined} disabled={busy || !all} onClick={() => onDone(Object.fromEntries(items.map(([key]) => [key, true])))}>
        {button}
      </button>
    </div>
  );
}

import { useState } from "react";
import Fold from "./Fold.jsx";
import { AuditTable } from "../screens/Audit";
import { foldLines, lensLines } from "./journey";
import { lensFor } from "./lens";
import Timeline, { LENSES } from "./Timeline";

const LENS_CHIPS = [["nurse", "Nurse"], ["doctor", "Doctor"], ["patient", "Patient"], ["everyone", "Everyone (audit)"]];

// The record, closed by default. Opening shows the role's lens, the other lenses and the audit.
// A deep-linked line opens it (R7: the fold state is never stored).
export default function History({ view, role, line, rows, rowsError, replaced, nowMs }) {
  const [open, setOpen] = useState(() => Boolean(line));
  const [picked, setPicked] = useState(null);
  const lens = open ? lensFor(role, picked) : lensFor(role, null);
  const everyone = lens === "everyone";
  const shownLens = lens in LENSES ? lens : "nurse";
  const kept = lensLines(view.timeline, view.nudges, shownLens, role, line);
  const { lines } = foldLines(kept, open);
  return (
    <Fold label="History" count={view.timeline.length} open={open} onToggle={() => setOpen(!open)}>
      <section aria-label="History">
        <div className="row" role="group" aria-label="Lens">
          {LENS_CHIPS.map(([id, name]) => (
            <button key={id} type="button" className="pill" aria-pressed={lens === id} onClick={() => setPicked({ role, lens: id })}>{name}</button>
          ))}
        </div>
        <div className="card">
          <p className="label">Timeline</p>
          {everyone ? (
            rowsError ? <p className="error" role="alert">Could not load the audit lines: {rowsError}</p>
            : rows.length ? <AuditTable rows={rows} /> : <p className="empty small">Nothing recorded for this patient yet.</p>
          ) : (
            <Timeline episodeId={view.episode?.id} lines={lines} nudges={view.nudges} replaced={replaced} lens={shownLens} role={role} line={line} nowMs={nowMs} />
          )}
        </div>
      </section>
    </Fold>
  );
}

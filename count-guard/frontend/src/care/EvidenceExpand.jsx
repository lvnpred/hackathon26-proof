import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { boxesAt, boxGroups, boxLabel, sawRows } from "./evidence.js";
import { Stage } from "./EvidenceStage.jsx";

const same = (a, b) => a?.concept === b?.concept && (a?.id ?? null) === (b?.id ?? null);

// The full-screen view of one check: a large picture with readable labels, a frame stepper, and a panel naming
// every box (tap one to light it up) and every box the AI ignored. Escape, Close or a click outside closes it.
export function EvidenceExpand({ title, images, start, frames, regions, countRows, rxRows, regionLines, onClose }) {
  const [shown, setShown] = useState(start);
  const [focus, setFocus] = useState(null);
  const close = useRef(null);
  useEffect(() => {
    close.current?.focus();
    const key = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = overflow; };
  }, [onClose]);
  const image = images[shown] || images[0];
  const boxes = image ? boxesAt(frames, image.t ?? image.index, true) : [];
  const saw = new Map(sawRows(countRows).map((r) => [r.concept, r]));
  const short = (g) => (saw.get(g.concept)?.missing > 0 ? 0 : 1);
  const { ignored, groups: all } = boxGroups(boxes);
  const groups = [...all].sort((a, b) => short(a) - short(b));
  const pick = (next) => setFocus(same(focus, next) ? null : next);
  return createPortal(
    <div className="ev-modal" role="dialog" aria-modal="true" aria-label={`${title}, expanded`} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ev-modal-body card">
        <div className="ev-modal-head">
          <p className="label">{title}</p>
          <button ref={close} type="button" onClick={onClose}>Close ✕</button>
        </div>
        <div className="ev-modal-grid">
          <div>
            {image && <Stage className="ev-stage ev-stage-big" image={image} boxes={boxes} regions={regions} rows={rxRows} expanded focus={focus} />}
            {images.length > 1 && (
              <div className="row ev-step">
                <button type="button" aria-label="Previous frame" disabled={shown === 0} onClick={() => setShown(shown - 1)}>◀</button>
                <span className="small">Frame {shown + 1} of {images.length}</span>
                <button type="button" aria-label="Next frame" disabled={shown === images.length - 1} onClick={() => setShown(shown + 1)}>▶</button>
              </div>
            )}
          </div>
          <aside className="ev-panel" aria-label="Every box">
            {groups.map((g) => {
              const row = saw.get(g.concept);
              return (
                <section key={g.concept}>
                  <button type="button" className="ev-saw-row" aria-pressed={same(focus, { concept: g.concept })} onClick={() => pick({ concept: g.concept })}>
                    <i className="ev-swatch" style={{ background: g.colour }} aria-hidden="true" />
                    <span>{row?.name || g.concept}</span>
                    <span className="muted">{g.boxes.length} boxed</span>
                    {row?.missing > 0 && <strong className="ev-missing">{row.missing} missing</strong>}
                  </button>
                  <ul className="ev-boxes">
                    {g.boxes.map((o) => (
                      <li key={o.id}>
                        <button type="button" aria-pressed={same(focus, { concept: o.label, id: o.id })} onClick={() => pick({ concept: o.label, id: o.id })}>
                          <b style={{ color: g.colour }}>{o.id}</b>{o.score != null && <span className="muted"> {o.score.toFixed(2)}</span>}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              );
            })}
            {ignored.length > 0 && (
              <section>
                <p className="label">Ignored by AI ({ignored.length})</p>
                <p className="small muted">Under the confidence cut-off, shown dashed.</p>
                <ul className="small">{ignored.map((o) => <li key={`${o.label}-${o.id}`}>{boxLabel(o)}</li>)}</ul>
              </section>
            )}
            {regionLines && <ul className="small">{regionLines.map((line, i) => <li key={i}>{line}</li>)}</ul>}
          </aside>
        </div>
      </div>
    </div>,
    document.body,
  );
}

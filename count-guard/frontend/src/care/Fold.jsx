export default function Fold({ label, count, open, onToggle, children }) {
  return (
    <section className="fold-block">
      <div className="fold-head">
        <span className="t-heading">{count === undefined ? label : `${label} · ${count}`}</span>
        <button className="quiet" aria-expanded={open} aria-label={`${open ? "Hide" : "Show"} ${label}`} onClick={onToggle}>{open ? "Hide" : "Show"}</button>
      </div>
      {open && children}
    </section>
  );
}

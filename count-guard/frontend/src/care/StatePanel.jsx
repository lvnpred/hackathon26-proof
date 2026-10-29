// Placeholder: one button per allowed move for the current role. Moves that need extra input are left to a later panel.
const BY = {
  doctor: "Dr. A. Rao (synthetic)",
  nurse: "Nurse Meena (synthetic)",
};

export default function StatePanel({ state, role, view, act, busy }) {
  const moves = (view.allowed || []).filter((move) => move.role === role && !(move.needs || []).length);
  return (
    <section className="card" aria-label="State">
      <p className="label">Moves from this state</p>
      {moves.length === 0 && <p className="empty small">No move is open for this role.</p>}
      <div className="row">
        {moves.map((move) => (
          <button key={move.to} type="button" disabled={busy} onClick={() => act("/state", { to: move.to, by: BY[role] })}>
            {move.label}
          </button>
        ))}
      </div>
    </section>
  );
}

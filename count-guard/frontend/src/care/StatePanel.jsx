import DoctorActions from "./DoctorActions";

const BY = {
  nurse: "Nurse Meena (synthetic)",
};

// Stopgap until the nurse and patient branches land: one button per allowed move that needs no extra input.
function MoveButtons({ role, view, act, busy }) {
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

// Actions for the open chart: one branch per role.
export default function StatePanel({ state, role, view, act, busy }) {
  switch (role) {
    case "doctor":
      return <DoctorActions state={state} view={view} act={act} busy={busy} />;
    // NurseActions and the patient branch replace MoveButtons in the next task.
    default:
      return <MoveButtons role={role} view={view} act={act} busy={busy} />;
  }
}

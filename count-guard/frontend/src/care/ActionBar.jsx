// The doctor's action buttons. Each one opens or closes its panel.
export default function ActionBar({ actions, isOpen, onToggle }) {
  if (actions.length === 0) return null;
  return (
    <div className="action-bar" role="group" aria-label="Doctor actions">
      {actions.map(([id, label]) => (
        <button key={id} type="button" aria-expanded={isOpen(id)} onClick={() => onToggle(id)}>{label}</button>
      ))}
    </div>
  );
}

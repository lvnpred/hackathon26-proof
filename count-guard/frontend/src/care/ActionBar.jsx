import { IconCamera, IconMic } from "./icons.jsx";

const ICONS = { orders: IconMic, photo: IconCamera };

// The doctor's quiet buttons. Each one opens or closes its panel.
export default function ActionBar({ actions, isOpen, onToggle }) {
  if (actions.length === 0) return null;
  return (
    <div className="action-bar" role="group" aria-label="Doctor actions">
      {actions.map(([id, label]) => {
        const Icon = ICONS[id];
        return (
          <button key={id} type="button" aria-expanded={isOpen(id)} onClick={() => onToggle(id)}>{Icon && <Icon />}{label}</button>
        );
      })}
    </div>
  );
}

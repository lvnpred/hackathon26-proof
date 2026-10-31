import { IconCheck, IconClock, IconWait, IconWarn } from "./icons.jsx";

const ICONS = { fine: IconCheck, wait: IconWait, check: IconClock, danger: IconWarn, done: null };

export default function StatusPill({ role, text }) {
  const Icon = ICONS[role];
  return (
    <span className={`status-pill s-${role}`}>
      {Icon && <Icon />}
      {text}
    </span>
  );
}

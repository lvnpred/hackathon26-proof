function Icon({ children }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

export function IconCheck() { return <Icon><path d="M5 12.5l4.5 4.5L19 7.5" /></Icon>; }
export function IconWait() { return <Icon><circle cx="12" cy="12" r="9" /><path d="M8 12h8" /></Icon>; }
export function IconClock() { return <Icon><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>; }
export function IconWarn() { return <Icon><path d="M12 3l10 18H2L12 3z" /><path d="M12 10v5M12 18v.5" /></Icon>; }
export function IconCamera() { return <Icon><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></Icon>; }
export function IconMic() { return <Icon><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></Icon>; }
export function IconUndo() { return <Icon><path d="M9 7L4 12l5 5" /><path d="M4 12h10a6 6 0 010 6h-3" /></Icon>; }
export function IconWhy() { return <Icon><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 114 2c-.9.6-1.5 1.1-1.5 2.2M12 17v.5" /></Icon>; }

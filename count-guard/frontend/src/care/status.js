import { H, M } from "./clock.js";

// The doctor's "My status" buttons. "auto" hands the chip back to the ward's own timing.
export const STATUS_CHOICES = [
  { id: "free1h", label: "Available for 1 h", status: "available", forMs: H },
  { id: "busy30", label: "Busy for 30 min", status: "busy", forMs: 30 * M },
  { id: "busy1h", label: "Busy for 1 h", status: "busy", forMs: H },
  { id: "auto", label: "Back to automatic", status: "auto", forMs: null },
];

export function statusBody(choice, nowMs, board, ids) {
  const until = choice.forMs == null ? null : nowMs + choice.forMs;
  return { board, ids, status: choice.status, until_ms: until, at_ms: nowMs };
}

export function statusQuery(board, ids, nowMs) {
  const q = `board=${encodeURIComponent(board)}&ids=${encodeURIComponent(ids.join(","))}&at_ms=${nowMs}`;
  return `/journey/staff/doctor?${q}`;
}

export function chipClass(status) {
  if (status === "in_theatre" || status === "busy") return "sun";
  return status === "available" ? "ready" : "info";
}

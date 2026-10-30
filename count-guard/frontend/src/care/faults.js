// A fault is one failed action, tied to the patient it was for and the action that raised it (its scope).
export const INBOX_SCOPES = ["/questions/", "/reviews/"];
export const NUDGE_SCOPES = ["/nudges/"];
export const CLOCK = "clock";
export const STATUS = "status";

export const makeFault = (episodeId, scope, message) => ({ episodeId, scope, message });

// The message when this fault belongs on this episode and action; otherwise "".
export function faultText(fault, episodeId, { only = null, except = [] } = {}) {
  if (!fault || fault.episodeId !== episodeId) return "";
  if (typeof fault.scope !== "string") return "";
  const starts = (prefix) => fault.scope.startsWith(prefix);
  if (only && !only.some(starts)) return "";
  if (except.some(starts)) return "";
  return fault.message;
}

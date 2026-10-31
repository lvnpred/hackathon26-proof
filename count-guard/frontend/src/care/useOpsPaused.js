import { useEffect, useState } from "react";
import { call } from "../journey";
import { canSeeAi } from "./ai.js";
import { SIGNED_IN } from "./people.js";

// Whether the ops agent is paused, and who switched it. paused is null until the server answers; staff only.
// toggle() posts the signed-in person's name, never an AI name (the backend rejects names that start with "AI").
export function useOpsPaused(role, nowMs) {
  const staff = canSeeAi(role);
  const [state, setState] = useState({ paused: null, by: null, atMs: null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!staff) return;
    call("/journey/ops")
      .then((o) => setState({ paused: Boolean(o.paused), by: o.by ?? null, atMs: o.at_ms ?? null }))
      .catch(() => setState({ paused: null, by: null, atMs: null }));
  }, [staff]);
  const toggle = () => {
    const verb = state.paused ? "resume" : "pause";
    setBusy(true);
    setError("");
    return call(`/journey/ops/${verb}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ by: SIGNED_IN[role].name, at_ms: nowMs }) })
      .then((o) => setState({ paused: Boolean(o.paused), by: o.by ?? null, atMs: o.at_ms ?? nowMs }))
      .catch(() => setError(`Could not ${verb} the AI.`))
      .finally(() => setBusy(false));
  };
  return staff ? { ...state, busy, error, toggle } : { paused: null, by: null, atMs: null, busy: false, error: "", toggle };
}

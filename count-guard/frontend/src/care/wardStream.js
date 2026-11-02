import { WARD_STREAM } from "./roster.js";

// Follow GET /journey/ward/stream (spec §8). Each change, the clock moving, and every (re)connect call
// onChange once per burst. EventSource reconnects by itself and sends Last-Event-ID; a reconnect may have missed
// a change, so it reads the ward again too. Returns stop(). Without EventSource it does nothing: the 3 s refresh
// in useWard still runs.
export function followWard(onChange, { Source = globalThis.EventSource, delayMs = 150 } = {}) {
  if (typeof Source !== "function") return () => {};
  let timer = null;
  let stopped = false;
  const soon = () => {
    if (stopped || timer) return;
    timer = setTimeout(() => {
      timer = null;
      if (!stopped) onChange();
    }, delayMs);
  };
  const source = new Source(WARD_STREAM);
  source.onmessage = soon;
  source.onopen = soon;
  source.addEventListener("clock", soon);
  return () => {
    stopped = true;
    clearTimeout(timer);
    source.close();
  };
}

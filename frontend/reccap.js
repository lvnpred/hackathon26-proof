"use strict";
// Dictation is capped (UI-A Task 3): from `warn` seconds the timer turns amber and the status says 30 seconds are left
// (once); at `max` seconds the recorder is stopped (once) and the normal stop path transcribes. app.js calls tick(s) from
// its 500 ms recording tick, for first dictations and corrections; the Spell it voice input has its own short cap.
// Loaded BEFORE app.js; also loads under node for tests.
(function (root) {
  const WARN_TEXT = "30 seconds left — finish the dictation.";
  const STOP_TEXT = "Stopped at 5 minutes — transcribing.";

  function create(o) {                                   // o: { max, warn, timer, status(msg), stop() }
    let warned = false, stopped = false;
    function tick(s) {
      if (s >= o.warn && !warned) {
        warned = true;
        if (o.timer) o.timer.classList.add("rec-warn");
        o.status(WARN_TEXT);
      }
      if (s >= o.max && !stopped) {
        stopped = true;
        o.stop();
        o.status(STOP_TEXT);
      }
    }
    function reset() {                                   // a new recording, or the recording UI ended
      warned = false;
      stopped = false;
      if (o.timer) o.timer.classList.remove("rec-warn");
    }
    return { tick, reset, capped: () => stopped, stopText: STOP_TEXT };
  }

  root.RecCap = { create };
})(typeof window !== "undefined" ? window : globalThis);

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { IDLE, createStepRunner, stepSlot } from "./modelStep.js";

// useModelStep({ capability, lens }) -> { step, lens, run, retry, startRecording, stopRecording, reset }.
// `run(fn, { what, upload })` calls fn({ onProgress, signal, timeoutMs }); the step goes uploading -> checking ->
// done or failed. The runner lives in modelStep.js (tested with a fake clock); this hook holds its step in React
// state. The runner is mounted in the effect, so StrictMode's mount -> cleanup -> mount leaves a live runner, a
// changed capability gets a new one, and unmount aborts any call in flight.
export function useModelStep({ capability, lens = "staff" } = {}) {
  const [step, setStep] = useState(IDLE);
  const cap = useRef(capability);
  cap.current = capability;
  const slot = useRef(null);
  if (!slot.current) slot.current = stepSlot(() => createStepRunner({ capability: cap.current, onChange: setStep }));

  useEffect(() => slot.current.mount(), [capability]);

  const run = useCallback((fn, opts) => slot.current.get().run(fn, opts), []);
  const retry = useCallback(() => slot.current.get().retry(), []);
  const startRecording = useCallback(() => slot.current.get().startRecording(), []);
  const stopRecording = useCallback(() => slot.current.get().stopRecording(), []);
  const reset = useCallback(() => slot.current.get().reset(), []);

  return useMemo(
    () => ({ step, lens, run, retry, startRecording, stopRecording, reset }),
    [step, lens, run, retry, startRecording, stopRecording, reset],
  );
}

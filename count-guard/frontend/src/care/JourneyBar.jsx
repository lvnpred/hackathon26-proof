import { journeySteps } from "./journey";

// Where the patient has been, is and goes next. The current step keeps the state words beside its name; a skipped step says Skipped.
export default function JourneyBar({ state, visited }) {
  return (
    <ol className="journey" aria-label="Journey">
      {journeySteps(state, visited).map((step) => (
        <li key={step.key} className={step.status} aria-current={step.status === "current" ? "step" : undefined}>
          {step.status === "done" && <><span aria-hidden="true">✓</span>{" "}</>}
          {step.label}
          {step.detail && <small>{step.detail}</small>}
        </li>
      ))}
    </ol>
  );
}

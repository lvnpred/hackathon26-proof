import { journeySteps } from "./journey";

// Where the patient has been, is and goes next. The current step keeps the state words as its second line.
export default function JourneyBar({ state, visited }) {
  return (
    <ol className="journey" aria-label="Journey">
      {journeySteps(state, visited).map((step) => (
        <li key={step.key} className={step.status} aria-current={step.status === "current" ? "step" : undefined}>
          {step.status === "done" && <><span aria-hidden="true">✓</span>{" "}</>}
          {step.label}
          {step.status === "current" && <small>{step.detail}</small>}
        </li>
      ))}
    </ol>
  );
}

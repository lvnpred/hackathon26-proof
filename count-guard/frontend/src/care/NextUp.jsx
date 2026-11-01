import { nextUp } from "./now.js";

// The patient's one line: what they must do, who acts next, or that nothing is needed.
export default function NextUp({ view }) {
  const { kind, text } = nextUp(view);
  return (
    <section className={`card next-up next-up-${kind}`} aria-label="What happens next">
      <p className="label">What happens next</p>
      <p className="t-heading">{text}</p>
    </section>
  );
}

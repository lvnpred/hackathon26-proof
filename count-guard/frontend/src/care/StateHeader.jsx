import JourneyBar from "./JourneyBar";
import NextCard from "./NextCard";
import { nextCard } from "./journey";

// Who the patient is and where they are. `you` adds the patient's own next-step card (the patient pages);
// staff charts show the card in the action panel instead.
export default function StateHeader({ patient, view, you = false }) {
  return (
    <header className="page-head state-head">
      <p className="label">Bed {patient.bed}</p>
      <h1>{patient.name}</h1>
      <JourneyBar state={view.state} visited={view.visited} />
      {you && <NextCard card={nextCard(view, "patient", { you: true })} />}
    </header>
  );
}

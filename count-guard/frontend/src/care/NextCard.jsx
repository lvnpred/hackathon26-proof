// The one next step: who owns it, what it is, and (for its owner) the buttons that do it.
export default function NextCard({ card, lead = null, footer = null, children }) {
  return (
    <section className="card next-card" aria-label="Next step">
      <p className="label">{card.eyebrow}</p>
      <p className="next-text">{card.text}</p>
      {lead}
      {card.mine && children}
      {card.waiting && <p className="note">{card.waiting}</p>}
      <p className="small muted">{card.last}</p>
      {footer}
    </section>
  );
}

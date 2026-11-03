// Why a card's action cannot run now (clarity §4.4): shown on the card, under its disabled buttons.
export default function Opens({ reason }) {
  return reason ? <p className="small muted opens">{reason}</p> : null;
}

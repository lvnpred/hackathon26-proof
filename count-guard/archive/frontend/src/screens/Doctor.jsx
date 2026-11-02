import { PageLead, Shell } from "../App";
import { subtitle, useJourney } from "../journey";
import ClinicPanel from "./ClinicPanel";

export default function Doctor() {
  const { view, error, busy, act } = useJourney();

  return (
    <Shell subtitle={subtitle(view)}>
      <PageLead
        kicker="Doctor"
        title="Prescribe, set the ward limits, sign the card."
        body="The prescription comes from Doctor Dictation as written. The ward limits are yours; the app only sets readings beside them. The discharge card is a clinic template you choose and sign."
      />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <section className="main">
          <ClinicPanel view={view} busy={busy} act={act} />
        </section>
      </div>
    </Shell>
  );
}

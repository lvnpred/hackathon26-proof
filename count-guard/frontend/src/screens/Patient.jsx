import { PageLead, Shell } from "../App";
import { subtitle, uploadJourney, useJourney } from "../journey";
import { Medicines, Nudges, Reminders, Strips } from "../care/legacy/TodayPanel";
import { CheckIn, MyCard, NeedHelp } from "../care/legacy/PatientCard";

export default function Patient() {
  const { view, setView, error, setError, busy, setBusy, act } = useJourney();

  async function upload(path, file) {
    if (!view) return null;
    setError("");
    setBusy(true);
    try {
      const next = await uploadJourney(view.episode.id, path, file);
      setView(next);
      return next;
    } finally {
      setBusy(false);
    }
  }

  const common = { view, busy: busy || !view, act };
  return (
    <Shell subtitle={subtitle(view)}>
      <div className="phone">
        <PageLead
          kicker="For the patient"
          title="Your medicines and your card."
          body="Plain words from what your doctor wrote. If something worries you, press Need help or call the help line."
        />
        {error && <p className="error" role="alert">{error}</p>}

        <>
              <Nudges {...common} />
              <section className="card">
                <p className="label">My medicines</p>
                <Medicines schedule={view?.schedule || []} />
                <Reminders {...common} />
              </section>
              <section className="card">
                <p className="label">Check my strips</p>
                <Strips {...common} upload={upload} />
              </section>
              <section className="card">
                <p className="label">My discharge card</p>
                <MyCard card={view?.card} />
              </section>
              <CheckIn card={view?.card} busy={common.busy} act={act} />
              <section className="card">
                <NeedHelp busy={common.busy} act={act} />
              </section>
        </>
      </div>
    </Shell>
  );
}

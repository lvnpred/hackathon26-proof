import { PageLead, Shell } from "../App";
import { subtitle, uploadJourney, useJourney } from "../journey";
import TodayPanel from "./TodayPanel";

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

  return (
    <Shell subtitle={subtitle(view)}>
      <div className="phone">
        <PageLead
          kicker="For the patient"
          title="Your medicines and your card."
          body="Plain words from what your doctor wrote. If something worries you, press Need help or call the help line."
        />
        {error && <p className="error" role="alert">{error}</p>}

        <TodayPanel view={view} busy={busy} act={act} upload={upload} />
      </div>
    </Shell>
  );
}

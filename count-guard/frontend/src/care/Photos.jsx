import { label } from "./clock";
import { photoCheckLabel } from "./drafts";

// Every photo on the chart, for every role. A mismatch is flagged, never hidden.
export default function Photos({ view }) {
  const photos = view.photos || [];
  if (!photos.length) return null;
  return (
    <section className="card" aria-label="Photos">
      <p className="label">Photos</p>
      <ul className="task-list">
        {photos.map((photo) => (
          <li key={photo.id}>
            <img src={photo.url} alt={`${photo.purpose} photo by ${photo.by}`} width={72} height={72} style={{ objectFit: "cover", borderRadius: 6 }} />
            <span className="small">
              {photo.purpose === "proof" ? "Proof" : "Reference"} · {photo.by} · {label(photo.at_ms)}
              {photo.check && (
                <>
                  <br />
                  <span className={`pill ${photo.check.match === "mismatch" ? "sun" : "info"}`}>{photoCheckLabel(photo.check)}</span>{" "}
                  {photo.check.why}
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

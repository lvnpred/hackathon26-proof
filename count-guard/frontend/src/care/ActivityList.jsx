import { Link } from "react-router-dom";
import AiMoment from "./AiMoment.jsx";

// Activity rows: patient · capability · the AI moment line. Reusable by the ops agent feed.
export default function ActivityList({ rows, role, empty = null }) {
  if (rows.length === 0) return <p className="empty small">{empty}</p>;
  return (
    <ul className="activity-list" aria-label="Activity">
      {rows.map(({ episodeId, patient, moment }) => (
        <li key={`${episodeId}:${moment.id}`}>
          <span className="small"><Link to={`/chart/${episodeId}`}>{patient}</Link> · {moment.title}</span>
          <AiMoment moment={moment} role={role} episodeId={episodeId} />
        </li>
      ))}
    </ul>
  );
}

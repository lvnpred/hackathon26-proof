// "28 Oct, 2:38 pm": when the line was written, beside the story clock.
function written(iso) {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return `written ${at.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}, ${at.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase()}`;
}

// Every line as written; a corrected line is struck through and tagged. The chart's Everyone lens reuses it.
export function AuditTable({ rows }) {
  return (
    <div className="table-box">
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th style={{ textAlign: "left" }}>Who</th>
            <th style={{ textAlign: "left" }}>What</th>
            <th>Tier</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const struck = Boolean(row.replaced_by);
            return (
              <tr key={row.id} className={struck ? "struck" : undefined}>
                <td className="num" style={{ whiteSpace: "nowrap" }}>
                  {row.when}
                  {row.written_at && <div className="small muted">{written(row.written_at)}</div>}
                </td>
                <td style={{ textAlign: "left" }}>{row.who || "—"}</td>
                <td style={{ textAlign: "left" }}>
                  {row.what}
                  {struck && <> <span className="tag">corrected</span></>}
                  {row.supersedes && <> <span className="tag info">correction</span></>}
                  <div className="small muted">{row.type}</div>
                </td>
                <td>{row.tier ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

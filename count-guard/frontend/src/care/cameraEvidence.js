// Plain lines for the camera evidence viewer. No event names reach the page.
const WORDS = {
  item_appeared: "Item seen",
  zone_changed: "Item moved",
  item_lost: "Item lost from view",
  identity_relink: "Item matched again",
};
const ZONES = { tray: "tray", field: "field", bucket: "bucket" };

export function trackLine(track) {
  const what = track.label || "Item";
  const where = ZONES[track.zone] ? ` in the ${ZONES[track.zone]}` : "";
  return `${what} ${track.track_id}${where}`;
}

export function cameraRows(events) {
  return (events || [])
    .filter((e) => WORDS[e.event_type])
    .map((e) => ({ id: e.id, text: `${Math.round((e.media_ts_ms || 0) / 1000)} s · ${WORDS[e.event_type]}${e.payload?.track_id ? ` (${e.payload.track_id})` : ""}` }));
}

import { IconCamera } from "./icons.jsx";

// One way to add a photo or clip: a button-looking label that opens the camera on a phone, and the plain file
// picker under it. The real input is visually hidden but stays in the region, so a file can be set on it directly.
export default function PhotoInput({ label = "Take photo", accept = "image/*", capture = true, multiple = false, disabled = false, onFiles }) {
  function pick(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (files.length) onFiles(files);
  }
  return (
    <div className="photo-field">
      <label className={`photo-input${disabled ? " disabled" : ""}`}>
        <IconCamera />
        {label}
        <input className="visually-hidden" type="file" accept={accept} capture={capture ? "environment" : undefined} multiple={multiple} disabled={disabled} onChange={pick} />
      </label>
      <span className="small">or upload a file</span>
    </div>
  );
}

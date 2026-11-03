import { useRef, useState } from "react";
import { IconCamera } from "./icons.jsx";
import CameraSheet from "./CameraSheet.jsx";

// One way to add a photo or clip. For a photo (`capture`) the button opens a small dialog with two choices, take a
// photo with the camera or upload a file; a computer ignores the HTML `capture` hint, so a bare file picker never
// offered the camera there. For a clip or several files the button is the plain file picker. The real inputs are
// visually hidden but stay in the region, so a file can be set on one directly.
export default function PhotoInput({ label = "Take photo", accept = "image/*", capture = true, multiple = false, disabled = false, onFiles }) {
  const [open, setOpen] = useState(false);
  const upload = useRef(null);
  const phone = useRef(null);

  function pick(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (files.length) {
      setOpen(false);
      onFiles(files);
    }
  }
  const input = (ref, extra = {}) => (
    <input ref={ref} className="visually-hidden" type="file" accept={accept} multiple={multiple} disabled={disabled} onChange={pick} tabIndex={-1} {...extra} />
  );

  if (!capture) {
    return (
      <div className="photo-field">
        <label className={`photo-input${disabled ? " disabled" : ""}`}>
          <IconCamera />
          {label}
          {input(null)}
        </label>
        <span className="small">or upload a file</span>
      </div>
    );
  }
  return (
    <div className="photo-field">
      <button type="button" className={`photo-input${disabled ? " disabled" : ""}`} disabled={disabled} onClick={() => setOpen(true)}>
        <IconCamera />
        {label}
      </button>
      {input(upload)}
      {input(phone, { capture: "environment" })}
      {open && (
        <CameraSheet
          onClose={() => setOpen(false)}
          onPhoto={(file) => { setOpen(false); onFiles([file]); }}
          onUpload={() => upload.current?.click()}
          onPhoneCamera={() => phone.current?.click()}
        />
      )}
    </div>
  );
}

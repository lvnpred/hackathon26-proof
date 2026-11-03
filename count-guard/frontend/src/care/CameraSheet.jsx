import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { IconCamera } from "./icons.jsx";

const CAN_STREAM = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

// Why the camera could not open, in words a person can act on.
export function cameraProblem(error) {
  const name = error?.name || "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Camera access is blocked. Allow it in the browser, or upload a file instead.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No camera was found. Upload a file instead.";
  return "The camera could not start. Upload a file instead.";
}

// The dialog behind "Take photo": two plain choices, then a live preview with one capture button.
// It never holds a file input; the parent owns those, so upload and the phone's camera app go through it.
export default function CameraSheet({ onClose, onPhoto, onUpload, onPhoneCamera }) {
  const [step, setStep] = useState("choose"); // choose | live
  const [note, setNote] = useState("");
  const [ready, setReady] = useState(false);
  const video = useRef(null);
  const stream = useRef(null);
  const first = useRef(null);

  function stop() {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }

  useEffect(() => {
    first.current?.focus();
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("keydown", onKey); stop(); };
  }, []);

  async function openCamera() {
    if (!CAN_STREAM) { onPhoneCamera(); return; }
    setNote("");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      setStep("live");
      requestAnimationFrame(() => {
        if (video.current) { video.current.srcObject = stream.current; video.current.play().catch(() => {}); }
      });
    } catch (error) {
      stop();
      setNote(cameraProblem(error));
    }
  }

  function capture() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d").drawImage(v, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) { setNote("The photo could not be taken. Try again."); return; }
      stop();
      onPhoto(new File([blob], `photo-${Date.now()}.jpg`, { type: "image/jpeg" }));
    }, "image/jpeg", 0.92);
  }

  function back() {
    stop();
    setReady(false);
    setStep("choose");
  }

  return createPortal(
    <div className="photo-sheet-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="photo-sheet card" role="dialog" aria-modal="true" aria-label="Add a photo">
        <div className="photo-sheet-head">
          <p className="label">{step === "live" ? "Take a photo" : "Add a photo"}</p>
          <button type="button" className="quiet" aria-label="Close" onClick={onClose}>✕</button>
        </div>
        {step === "choose" && (
          <>
            {note && <p className="photo-sheet-note" role="alert">{note}</p>}
            <div className="photo-sheet-choices">
              <button ref={first} type="button" className="photo-choice" onClick={openCamera}>
                <IconCamera />
                <span><b>Take a photo</b><br /><span className="small muted">Use this device's camera</span></span>
              </button>
              <button type="button" className="photo-choice" onClick={onUpload}>
                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M5 20h14" /></svg>
                <span><b>Upload a file</b><br /><span className="small muted">Pick a picture from this device</span></span>
              </button>
            </div>
            <button type="button" className="quiet" onClick={onClose}>Cancel</button>
          </>
        )}
        {step === "live" && (
          <>
            <div className="photo-sheet-view">
              <video ref={video} playsInline muted onLoadedData={() => setReady(true)} aria-label="Camera preview" />
              {!ready && <p className="small muted photo-sheet-wait">Starting the camera…</p>}
            </div>
            {note && <p className="photo-sheet-note" role="alert">{note}</p>}
            <div className="row">
              <button type="button" onClick={back}>Back</button>
              <button type="button" className="photo-capture" disabled={!ready} onClick={capture}>Capture</button>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body,
  );
}

// The pure parts of Dictate (care-app clarity §4.1, §4.3), so they can be tested without a browser.

// Hear one recording through the card's voice step: "Uploading recording… n%", then "Checking with Muse Voice… s".
// onHear(file, opts) gets the step's { onProgress, signal, timeoutMs }; Retry sends the same file again.
export function hearWith(step, onHear, file) {
  return step.run((opts) => onHear(file, opts), { what: "recording" });
}

// The source words under the box: the heard words stay voice until Send, and say "edited" once they differ.
export function heardWords(words, heardText, text) {
  const edited = String(heardText || "").trim() !== String(text || "").trim();
  return edited ? `${words} · edited` : words;
}

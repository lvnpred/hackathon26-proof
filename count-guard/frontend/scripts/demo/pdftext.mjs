// The text a PDF draws, enough for the demo check to find words in the discharge PDF (fpdf2: Flate streams,
// literal strings shown with Tj/TJ). Not a general PDF reader.
import { inflateSync } from "node:zlib";

const unescape = (s) => s.replace(/\\([nrtbf()\\]|[0-7]{1,3})/g, (_, c) => {
  if (/^[0-7]+$/.test(c)) return String.fromCharCode(parseInt(c, 8));
  return { n: "\n", r: "\r", t: "\t", b: "\b", f: "\f" }[c] ?? c;
});

// Every content stream, inflated when it is Flate-encoded, then the literal strings inside, joined by spaces.
export function pdfText(buffer) {
  const raw = Buffer.from(buffer).toString("latin1");
  const parts = [];
  const re = /<<([^]*?)>>\s*stream\r?\n/g;
  let m;
  while ((m = re.exec(raw))) {
    const start = m.index + m[0].length;
    const end = raw.indexOf("endstream", start);
    if (end < 0) break;
    let body = Buffer.from(raw.slice(start, end).replace(/\r?\n$/, ""), "latin1");
    if (/\/FlateDecode/.test(m[1])) {
      try { body = inflateSync(body); } catch { continue; }
    }
    const text = body.toString("latin1");
    for (const s of text.matchAll(/\(((?:\\.|[^\\)])*)\)\s*Tj|\[((?:[^\]])*)\]\s*TJ/g)) {
      if (s[1] !== undefined) parts.push(unescape(s[1]));
      else parts.push([...s[2].matchAll(/\(((?:\\.|[^\\)])*)\)/g)].map((x) => unescape(x[1])).join(""));
    }
    re.lastIndex = end;
  }
  return parts.join(" ").replace(/\s+/g, " ");
}

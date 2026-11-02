import test from "node:test";
import assert from "node:assert/strict";
import { deflateSync } from "node:zlib";
import { pdfText } from "./pdftext.mjs";

const pdf = (content, flate) => {
  const body = flate ? deflateSync(Buffer.from(content, "latin1")) : Buffer.from(content, "latin1");
  return Buffer.concat([
    Buffer.from(`%PDF-1.3\n1 0 obj\n<</Length ${body.length}${flate ? " /Filter /FlateDecode" : ""}>>\nstream\n`, "latin1"),
    body,
    Buffer.from("\nendstream\nendobj\n%%EOF\n", "latin1"),
  ]);
};

test("reads Tj strings from a Flate stream", () => {
  const text = pdfText(pdf("BT (Drugs given: lignocaine 2%) Tj ET BT (Opened 15. Returned 15.) Tj ET", true));
  assert.match(text, /lignocaine 2%/);
  assert.match(text, /Opened 15\. Returned 15\./);
});

test("reads TJ arrays and escapes in a plain stream", () => {
  assert.equal(pdfText(pdf("BT [(Swab ) -20 (count \\(saved\\))] TJ ET", false)), "Swab count (saved)");
});

test("a PDF without text gives empty text", () => {
  assert.equal(pdfText(pdf("0 0 m 10 10 l S", true)), "");
});

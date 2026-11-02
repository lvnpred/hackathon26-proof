import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { cameraRows, trackLine } from "./cameraEvidence.js";

test("camera rows use plain words, not event names", () => {
  const rows = cameraRows([
    { id: "1", event_type: "zone_changed", media_ts_ms: 4200, payload: { track_id: "t1" } },
    { id: "2", event_type: "something_else", media_ts_ms: 1, payload: {} },
  ]);
  assert.deepEqual(rows, [{ id: "1", text: "4 s · Item moved (t1)" }]);
  assert.equal(trackLine({ track_id: "t1", label: "lap sponge", zone: "bucket" }), "lap sponge t1 in the bucket");
});

test("the Inspector shows camera evidence to staff only", () => {
  const s = fs.readFileSync(new URL("./Inspector.jsx", import.meta.url), "utf8");
  assert.match(s, /lens !== "patient" && tab === "evidence" && moment\.capability === "swabs" && <CameraEvidence/);
});

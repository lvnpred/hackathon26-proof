import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { OLD_NAV, OLDER_SCREENS, RETIRED } from "./older.js";

test("no menu entry leads to the retired /play screen", () => {
  const paths = [...OLD_NAV, ...OLDER_SCREENS].map(([path]) => path);
  for (const retired of RETIRED) assert.ok(!paths.includes(retired), `${retired} is still in a menu`);

  const app = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
  assert.ok(app.includes('path="/journey"'), "the route must stay (code kept)");
  assert.match(app, /import \{[^}]*OLD_NAV[^}]*OLDER_SCREENS[^}]*\} from "\.\/care\/older"/);
  assert.ok(!app.includes('NavLink to="/journey"'), "no nav link to /journey");
});

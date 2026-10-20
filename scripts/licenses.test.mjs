import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { evaluate, isExpressionAllowed } from "./lib/licenses.mjs";

const policy = JSON.parse(readFileSync(new URL("./license-policy.json", import.meta.url), "utf8"));
const allowed = new Set(policy.allowed);

test("simple ids", () => {
  assert.equal(isExpressionAllowed("MIT", allowed), true);
  assert.equal(isExpressionAllowed("GPL-3.0-only", allowed), false);
  assert.equal(isExpressionAllowed("AGPL-3.0-or-later", allowed), false);
});

test("OR passes if either side is allowed, AND needs both", () => {
  assert.equal(isExpressionAllowed("GPL-2.0 OR MIT", allowed), true);
  assert.equal(isExpressionAllowed("MIT AND GPL-2.0", allowed), false);
  assert.equal(isExpressionAllowed("(MIT AND ISC) OR GPL-2.0", allowed), true);
  assert.equal(isExpressionAllowed("MIT AND (GPL-2.0 OR ISC)", allowed), true);
});

test("malformed expressions throw", () => {
  assert.throws(() => isExpressionAllowed("MIT OR", allowed));
  assert.throws(() => isExpressionAllowed("(MIT", allowed));
});

test("missing metadata is a violation, not a pass", () => {
  for (const license of ["UNKNOWN", "UNLICENSED", "", undefined]) {
    const { violations } = evaluate([{ name: "x", license }], policy, "node");
    assert.equal(violations.length, 1, String(license));
  }
});

test("aliases map free-text Python licenses", () => {
  const entries = [
    { name: "a", license: "MIT License" },
    { name: "b", license: "BSD License" },
    { name: "c", license: "Apache-2.0 OR BSD-2-Clause" },
  ];
  assert.deepEqual(evaluate(entries, policy, "python").violations, []);
});

test("copyleft and unlisted licenses are rejected", () => {
  const entries = [
    { name: "a", license: "AGPL-3.0" },
    { name: "b", license: "SSPL-1.0" },
    { name: "c", license: "BUSL-1.1" },
  ];
  assert.equal(evaluate(entries, policy, "node").violations.length, 3);
});

test("exceptions are per ecosystem, package and exact license", () => {
  const ok = evaluate([{ name: "lightningcss-linux-x64-gnu", license: "MPL-2.0" }], policy, "node");
  assert.deepEqual(ok.violations, []);
  assert.equal(ok.excepted.length, 1);
  const wrongEcosystem = evaluate([{ name: "lightningcss", license: "MPL-2.0" }], policy, "python");
  assert.equal(wrongEcosystem.violations.length, 1);
  assert.equal(evaluate([{ name: "other", license: "MPL-2.0" }], policy, "node").violations.length, 1);
  assert.equal(evaluate([{ name: "certifi", license: "AGPL-3.0" }], policy, "python").violations.length, 1);
});

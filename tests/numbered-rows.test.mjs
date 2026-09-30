import assert from "node:assert/strict";
import test from "node:test";
import {numberedRows} from "../app/static/numbered-rows.mjs";

test("blank label generates plain numbered score rows", () => {
  assert.deepEqual(numberedRows("  ", 1, 3), ["1", "2", "3"]);
});

test("a label still prefixes each numbered row", () => {
  assert.deepEqual(numberedRows(" Round ", 4, 2), ["Round 4", "Round 5"]);
});

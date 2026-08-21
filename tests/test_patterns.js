#!/usr/bin/env node
// Unit tests for the Key Guard key-detection patterns (no browser required).
// Run: node tests/test_patterns.js
"use strict";

const { redact, hasKey } = require("../extension/patterns.js");

const cases = [
  // [text, hasKey?, expectedRedact]
  ["sk-test-1234567890abcdef", true, "{{REDACTED}}"],
  ["sk-ant-api03-abcdefghijklmnop", true, "{{REDACTED}}"],
  ["ghp_1234567890abcdefghijklmnopqrstuvwxyz", true, "{{REDACTED}}"],
  ["github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZ012345", true, "{{REDACTED}}"],
  ["AIzaSyA1234567890abcdefghijklmnopqrstuvwxyz12", true, "{{REDACTED}}"],
  ["xoxb-1234567890-abcdefghijkl", true, "{{REDACTED}}"],
  ["AKIA1234567890ABCDEF", true, "{{REDACTED}}"],
  ["sk_live_1234567890abcdefghijklmnop", true, "{{REDACTED}}"],
  ["eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz123456", true, "{{REDACTED}}"],
  ["just a normal sentence without keys", false, "just a normal sentence without keys"],
  ["prefix key=sk-real-abcdefghijklmnop1234 suffix", true, "prefix key={{REDACTED}} suffix"],
];

let pass = 0;
for (const [text, expectKey, expectOut] of cases) {
  const has = hasKey(text);
  const out = redact(text);
  const ok = has === expectKey && out === expectOut;
  console.log((ok ? "PASS" : "FAIL") + " | " + JSON.stringify(text.slice(0, 48)));
  if (!ok) {
    console.log("   hasKey:", has, "expected", expectKey);
    console.log("   redact:", JSON.stringify(out));
  }
  if (ok) pass += 1;
}

console.log(`\n${pass}/${cases.length} pattern cases passed`);
process.exit(pass === cases.length ? 0 : 1);

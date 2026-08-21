// Shared API-key detection patterns for the Key Guard extension.
// Loadable both as a content-script global and as a Node module (for tests).
(function (root, factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else {
    root.GuardPatterns = factory();
  }
})(typeof self !== "undefined" ? self : globalThis, function () {
  // Common API key / token formats. The JWT-like branch is intentionally broad;
  // false positives just produce a redaction warning.
  const SOURCE =
    "sk-[A-Za-z0-9_\\-]{16,}" +          // OpenAI
    "|sk-ant-[A-Za-z0-9_\\-]{10,}" +     // Anthropic
    "|ghp_[A-Za-z0-9]{30,}" +            // GitHub classic
    "|github_pat_[A-Za-z0-9_]{20,}" +    // GitHub fine-grained
    "|AIza[0-9A-Za-z_\\-]{30,}" +        // Google
    "|xox[baprs]-[A-Za-z0-9\\-]{10,}" +  // Slack
    "|AKIA[0-9A-Z]{16}" +                // AWS access key
    "|sk_live_[0-9a-zA-Z]{16,}" +        // Stripe live
    "|sk_test_[0-9a-zA-Z]{16,}" +        // Stripe test
    "|[A-Za-z0-9_\\-]{20,}\\.[A-Za-z0-9_\\-]{20,}\\.[A-Za-z0-9_\\-]{16,}"; // JWT-like

  const PATTERN = new RegExp(SOURCE, "g");

  function redact(text, replacement) {
    const place = replacement || "{{REDACTED}}";
    return text.replace(PATTERN, () => place);
  }

  function hasKey(text) {
    PATTERN.lastIndex = 0;
    return PATTERN.test(text);
  }

  return { PATTERN, SOURCE, redact, hasKey };
});

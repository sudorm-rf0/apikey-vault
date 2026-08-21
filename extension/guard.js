// Key Guard content script: watches paste/input in text fields and redacts
// API keys so they can never end up in an AI chat in plaintext.

(function () {
  if (window.__guardInstalled) return;
  window.__guardInstalled = true;

  const patterns = window.GuardPatterns;
  const PLACEHOLDER = "{{REDACTED}}";

  // ---- toast UI ----------------------------------------------------------
  let toast = null;
  let toastTimer = null;

  function showToast(message, kind) {
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "guard-toast";
      document.documentElement.appendChild(toast);
    }
    toast.textContent = "";
    const icon = document.createElement("span");
    icon.textContent = kind === "blocked" ? "⛔" : "⚠️";
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(icon);
    toast.appendChild(text);
    toast.className = "guard-toast " + (kind || "info");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(hideToast, 6000);
  }

  function hideToast() {
    if (toast) toast.remove();
    toast = null;
  }

  // ---- replacement -------------------------------------------------------
  function resolveName(value) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "guard:resolve", value }, (resp) => {
          if (chrome.runtime.lastError) return resolve(null);
          resolve(resp && resp.name ? resp.name : null);
        });
      } catch (_) {
        resolve(null);
      }
    });
  }

  // Replace every key occurrence; when vault integration is enabled, matching
  // keys become {{vault:NAME}} instead of {{REDACTED}}.
  async function redactWithVault(text) {
    const re = new RegExp(patterns.PATTERN.source, "g");
    const seen = new Map();
    for (const m of text.matchAll(re)) {
      if (!seen.has(m[0])) seen.set(m[0], PLACEHOLDER);
    }
    for (const value of seen.keys()) {
      const name = await resolveName(value);
      if (name) seen.set(value, "{{vault:" + name + "}}");
    }
    return text.replace(new RegExp(patterns.PATTERN.source, "g"), (v) => seen.get(v) || PLACEHOLDER);
  }

  // ---- input handling ----------------------------------------------------
  function isEditable(el) {
    if (!el || el.isContentEditable) return !!el;
    const tag = el.tagName;
    return tag === "TEXTAREA" || (tag === "INPUT" && /^(text|search|url|email)$/.test(el.type));
  }

  function setElementValue(el, value) {
    if (el.isContentEditable) {
      el.textContent = value;
    } else {
      el.value = value;
    }
  }

  function getElementValue(el) {
    return el.isContentEditable ? el.textContent || "" : el.value || "";
  }

  // Insert text at the current caret/selection (textarea/input/contenteditable).
  function insertAtCursor(el, text) {
    if (el.isContentEditable) {
      const sel = window.getSelection();
      if (sel && sel.rangeCount > 0) {
        const range = sel.getRangeAt(0);
        range.deleteContents();
        range.insertNode(document.createTextNode(text));
        range.collapse(false);
      } else {
        el.textContent = (el.textContent || "") + text;
      }
      return;
    }
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const next = el.value.slice(0, start) + text + el.value.slice(end);
    el.value = next;
    const pos = start + text.length;
    el.setSelectionRange(pos, pos);
  }

  function placeCaretAtEnd(el) {
    try {
      if (el.isContentEditable) {
        const range = document.createRange();
        range.selectNodeContents(el);
        range.collapse(false);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      } else {
        const len = el.value.length;
        el.setSelectionRange(len, len);
      }
    } catch (_) {}
  }

  // Paste: intercept before insertion so the key never hits the field.
  document.addEventListener("paste", async (event) => {
    const el = event.target;
    if (!isEditable(el)) return;
    const text = event.clipboardData && event.clipboardData.getData("text/plain");
    if (!text || !patterns.hasKey(text)) return;

    event.preventDefault();
    event.stopPropagation();

    const redacted = await redactWithVault(text);
    insertAtCursor(el, redacted);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    showToast(
      "Pasted API key was blocked" +
        (redacted.includes("vault:") ? " and replaced with the vault placeholder. Use it and the agent can fetch the key via `apivault get`." : " and replaced with {{REDACTED}}. Never paste keys into an AI chat."),
      "blocked"
    );
  }, true);

  // Input: catch keys typed or inserted by other means (drop, autofill…).
  document.addEventListener("input", (event) => {
    const el = event.target;
    if (!isEditable(el)) return;
    const value = getElementValue(el);
    if (!patterns.hasKey(value)) return;

    const redacted = patterns.redact(value, PLACEHOLDER);
    setElementValue(el, redacted);
    placeCaretAtEnd(el);
    showToast(
      "API key detected and redacted in this field. Use the vault placeholder instead of plaintext.",
      "blocked"
    );
  }, true);
})();

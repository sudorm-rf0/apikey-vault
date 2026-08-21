/* apikey-vault GUI controller.
   All state lives in memory / sessionStorage; only the API token is persisted
   for the current tab session (cleared on close or Lock). */

"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  token: null,
  unlocked: false,
  keys: [],
  selected: null,     // key name
  revealed: false,
  filter: "",
};

let statusTimer = null;
let revealTimer = null;

/* ------------------------------------------------------------ API client */
async function api(method, path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  let body;
  if (opts.raw !== undefined) {
    body = opts.raw; // raw bytes (import)
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, { method, headers, body });
  if (res.status === 401 && !opts.noAuthReset) {
    // token no longer valid -> force lock screen
    sessionStorage.removeItem("apivault_token");
    state.token = null;
    if (state.unlocked) setLocked(true);
  }
  return res;
}

async function apiJson(method, path, opts = {}) {
  const res = await api(method, path, opts);
  let data = null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) data = await res.json();
  return { status: res.status, data };
}

function showScreen(name) {
  $("init-screen").hidden = name !== "init";
  $("unlock-screen").hidden = name !== "unlock";
  $("vault-screen").hidden = name !== "vault";
}

/* ------------------------------------------------------------- status bar */
function setStatus(text, kind = "") {
  const el = $("status-text");
  el.textContent = text;
  el.className = "status-text" + (kind ? " " + kind : "");
  clearTimeout(statusTimer);
  if (kind !== "error") {
    statusTimer = setTimeout(() => {
      el.textContent = "Ready.";
      el.className = "status-text";
    }, 5000);
  }
}

/* ------------------------------------------------------- lock state views */
async function setLocked(locked) {
  state.unlocked = !locked;
  state.selected = null;
  state.revealed = false;
  clearTimeout(revealTimer);

  $("app").classList.toggle("unlocked", !locked);
  $("lock-label").textContent = locked ? "LOCKED" : "UNLOCKED";
  showScreen(locked ? "unlock" : "vault");
  $("lock-btn").hidden = locked;
  $("change-pw-btn").hidden = locked;
  $("export-btn").hidden = locked;
  $("import-btn").hidden = locked;

  if (locked) {
    $("unlock-password").value = "";
    $("unlock-error").hidden = true;
    $("paste-input").value = "";
    $("paste-name").value = "";
    $("paste-desc").value = "";
    $("paste-status").textContent = "";
    $("reveal-warning").hidden = true;
    showPasteBox(false);
    $("unlock-password").focus();
  } else {
    setStatus("Vault unlocked.");
    await loadKeys();
  }
}

/* ------------------------------------------------------------- key list */
function renderList() {
  const list = $("key-list");
  list.textContent = "";
  const filter = state.filter.trim().toLowerCase();
  const keys = state.keys.filter((k) => {
    if (!filter) return true;
    return (
      k.name.toLowerCase().includes(filter) ||
      (k.description || "").toLowerCase().includes(filter)
    );
  });

  if (keys.length === 0) {
    const li = document.createElement("li");
    li.className = "empty-list";
    li.textContent = state.keys.length === 0 ? "No keys yet." : "No keys match the filter.";
    list.appendChild(li);
  } else {
    for (const k of keys) {
      const li = document.createElement("li");
      li.className = k.name === state.selected ? "selected" : "";
      const name = document.createElement("span");
      name.className = "key-name";
      name.textContent = k.name;
      const desc = document.createElement("span");
      desc.className = "key-desc";
      desc.textContent = k.description || "";
      li.append(name, desc);
      li.addEventListener("click", () => selectKey(k.name));
      list.appendChild(li);
    }
  }
  $("key-count").textContent = String(state.keys.length);
}

function selectKey(name) {
  state.selected = name;
  state.revealed = false;
  clearTimeout(revealTimer);
  const key = state.keys.find((k) => k.name === name);
  if (!key) return;

  $("empty-detail").hidden = true;
  $("editor").hidden = true;
  showPasteBox(true);
  $("key-detail").hidden = false;
  $("detail-name").textContent = key.name;
  $("detail-desc").textContent = key.description || "—";
  $("detail-created").textContent = key.created_at;
  $("detail-updated").textContent = key.updated_at;
  setRevealButton(false);
  setMasked();
  $("reveal-warning").hidden = true;
  renderList();
}

function setMasked() {
  $("detail-value").textContent = "••••••••••••••••••••••••••••";
}

function setRevealButton(revealed) {
  const btn = $("reveal-btn");
  btn.textContent = "";
  btn.appendChild(svgIcon(revealed ? "i-eye-off" : "i-eye"));
  btn.appendChild(document.createTextNode(revealed ? "Hide" : "Reveal"));
  $("reveal-inline").textContent = revealed ? "Hide" : "Reveal";
}

function svgIcon(symbolId) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#" + symbolId);
  svg.appendChild(use);
  return svg;
}

async function loadKeys() {
  const { status, data } = await apiJson("GET", "/v1/keys");
  if (status !== 200) {
    setStatus("Failed to load keys: " + (data?.error || status), "error");
    return;
  }
  state.keys = data.keys;
  state.selected = null;
  renderList();
  showEmptyDetail();
}

function showEmptyDetail() {
  $("key-detail").hidden = true;
  $("editor").hidden = true;
  showPasteBox(true);
  $("empty-detail").hidden = false;
  $("empty-text").textContent =
    state.keys.length === 0 ? "No keys yet — add one." : "Select a key to view it.";
}

/* ------------------------------------------------------- paste a key */
function showPasteBox(show) {
  $("paste-box").hidden = !show;
}

function unquoteValue(s) {
  let v = s.trim();
  if (
    (v.startsWith('"') && v.endsWith('"')) ||
    (v.startsWith("'") && v.endsWith("'"))
  ) {
    v = v.slice(1, -1);
  }
  return v;
}

/* Parse pasted text into [{name, value}].
   Accepts one or more `NAME=value` lines (optionally prefixed with `export `,
   values may be quoted), or a single bare value combined with the name field. */
function parsePasted(text, nameField) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const entries = [];
  for (const line of lines) {
    const m = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*)$/);
    if (m) {
      entries.push({ name: m[1], value: unquoteValue(m[2]) });
    } else {
      if (lines.length > 1) {
        throw new Error("line has no NAME= prefix: " + line.slice(0, 40));
      }
      if (!nameField) {
        throw new Error("enter a key name for the pasted value");
      }
      entries.push({ name: nameField, value: unquoteValue(line) });
    }
  }
  return entries;
}

async function onPasteSave() {
  const text = $("paste-input").value;
  const nameField = $("paste-name").value.trim();
  const desc = $("paste-desc").value.trim();
  $("paste-status").textContent = "";
  if (!text.trim()) {
    setStatus("Paste a key first.", "error");
    return;
  }
  let entries;
  try {
    entries = parsePasted(text, nameField);
  } catch (err) {
    $("paste-status").textContent = err.message;
    setStatus("Cannot parse paste: " + err.message, "error");
    return;
  }
  let created = 0;
  let updated = 0;
  for (const entry of entries) {
    const res = await api("PUT", "/v1/keys/" + encodeURIComponent(entry.name), {
      body: { value: entry.value, description: desc || undefined },
    });
    if (res.status === 201) created += 1;
    else if (res.status === 200) updated += 1;
    else {
      setStatus("Failed to save " + entry.name + ": " + (await safeError(res)), "error");
      return;
    }
  }
  $("paste-input").value = "";
  $("paste-name").value = "";
  $("paste-status").textContent = "";
  await loadKeys();
  selectKey(entries[0].name);
  const msg = created > 0 ? "Stored " + created + " key" + (created === 1 ? "" : "s") : "";
  const upd = updated > 0 ? (msg ? ", updated " + updated : "Updated " + updated) : "";
  setStatus(msg + upd + ".", "ok");
}

/* ---------------------------------------------------------------- editor */
function openEditor(mode, key) {
  $("key-detail").hidden = true;
  $("empty-detail").hidden = true;
  showPasteBox(false);
  $("editor").hidden = false;
  $("editor-title").textContent = mode === "add" ? "Add key" : "Rename key";
  $("edit-name").value = key ? key.name : "";
  $("edit-desc").value = key ? key.description || "" : "";
  $("edit-value").value = "";
  $("edit-value").hidden = mode === "rename";
  $("edit-value").parentElement.hidden = mode === "rename";
  $("edit-name").focus();
}

async function onEditorSave(e) {
  e.preventDefault();
  const name = $("edit-name").value.trim();
  const desc = $("edit-desc").value.trim();
  const value = $("edit-value").value;
  if (!name) {
    setStatus("Name is required.", "error");
    return;
  }

  if (state.selected && $("editor-title").textContent === "Rename key") {
    // rename = read old value -> PUT new -> DELETE old
    const oldName = state.selected;
    if (oldName === name) {
      setStatus("Name unchanged.", "error");
      return;
    }
    const getRes = await api("GET", "/v1/keys/" + encodeURIComponent(oldName));
    if (getRes.status !== 200) {
      setStatus("Could not read the original key.", "error");
      return;
    }
    const oldVal = (await getRes.json()).value;
    const putRes = await api("PUT", "/v1/keys/" + encodeURIComponent(name), {
      body: { value: oldVal, description: desc },
    });
    if (putRes.status !== 200 && putRes.status !== 201) {
      setStatus("Rename failed: " + (await safeError(putRes)), "error");
      return;
    }
    await api("DELETE", "/v1/keys/" + encodeURIComponent(oldName));
    setStatus(`Renamed ${oldName} → ${name}.`, "ok");
  } else {
    if (!value) {
      setStatus("Value is required.", "error");
      return;
    }
    const res = await api("PUT", "/v1/keys/" + encodeURIComponent(name), {
      body: { value, description: desc },
    });
    if (res.status !== 200 && res.status !== 201) {
      setStatus("Save failed: " + (await safeError(res)), "error");
      return;
    }
    setStatus(
      res.status === 201 ? `Stored ${name}.` : `Updated ${name}.`,
      "ok"
    );
  }
  $("edit-value").value = "";
  await loadKeys();
  selectKey(name);
}

async function safeError(res) {
  try {
    const data = await res.json();
    return data.error || res.status;
  } catch {
    return res.status;
  }
}

/* ----------------------------------------------------------- reveal/copy */
async function revealValue() {
  if (state.revealed) {
    setMasked();
    state.revealed = false;
    setRevealButton(false);
    $("reveal-warning").hidden = true;
    return;
  }
  const name = state.selected;
  if (!name) return;
  const res = await api("GET", "/v1/keys/" + encodeURIComponent(name));
  if (res.status !== 200) {
    setStatus("Could not read value: " + (await safeError(res)), "error");
    return;
  }
  const value = (await res.json()).value;
  $("detail-value").textContent = value;
  state.revealed = true;
  setRevealButton(true);
  $("reveal-warning").hidden = false;
  clearTimeout(revealTimer);
  revealTimer = setTimeout(() => {
    if (state.revealed) {
      setMasked();
      state.revealed = false;
      setRevealButton(false);
      $("reveal-warning").hidden = true;
    }
  }, 60000);
}

// Safe copy: put a placeholder on the clipboard so the real key can never be
// pasted into an AI chat by accident.
async function copyValue() {
  const name = state.selected;
  if (!name) return;
  const placeholder = "{{" + name + "}}";
  const ok = await copyText(placeholder);
  setStatus(
    ok
      ? `Copied placeholder ${placeholder} (safe). For the real value use “Plaintext…” — never paste keys into AI chats.`
      : "Copy failed.",
    ok ? "ok" : "error"
  );
}

// Explicit, warned plaintext copy.
async function copyPlaintext() {
  const name = state.selected;
  if (!name) return;
  const confirmed = await showModal({
    title: "Copy plaintext key",
    body: `<p>The real value of <strong></strong> will be put on the clipboard. Never paste it into an AI chat — use the placeholder <code>{{name}}</code> instead.</p>`,
    bodyName: name,
    actions: [
      { label: "Cancel" },
      { label: "Copy plaintext", danger: true, value: true },
    ],
  });
  if (!confirmed) return;
  const res = await api("GET", "/v1/keys/" + encodeURIComponent(name));
  if (res.status !== 200) {
    setStatus("Could not read value: " + (await safeError(res)), "error");
    return;
  }
  const value = (await res.json()).value;
  const ok = await copyText(value);
  setStatus(
    ok
      ? `Plaintext ${name} copied. ⚠ Do not paste it into AI chats — it stays on the clipboard until replaced.`
      : "Copy failed.",
    ok ? "error" : "error"
  );
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.className = "clipboard-helper";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------ delete */
async function deleteSelected() {
  const name = state.selected;
  if (!name) return;
  const confirmed = await showModal({
    title: "Delete key",
    body: `<p>Delete <strong></strong>? This cannot be undone.</p>`,
    bodyName: name,
    actions: [
      { label: "Cancel" },
      { label: "Delete", danger: true, value: true },
    ],
  });
  if (!confirmed) return;
  const res = await api("DELETE", "/v1/keys/" + encodeURIComponent(name));
  if (res.status !== 200) {
    setStatus("Delete failed: " + (await safeError(res)), "error");
    return;
  }
  setStatus(`Deleted ${name}.`, "ok");
  await loadKeys();
}

/* ------------------------------------------------------ change password */
async function changePassword() {
  const confirmed = await showModal({
    title: "Change master password",
    body: `
      <form id="cp-form" autocomplete="off">
        <div class="form-grid">
          <label>Old password
            <input type="password" id="cp-old" autocomplete="current-password">
          </label>
          <label></label>
          <label>New password
            <input type="password" id="cp-new" autocomplete="new-password">
          </label>
          <label>Confirm new password
            <input type="password" id="cp-confirm" autocomplete="new-password">
          </label>
        </div>
      </form>`,
    actions: [
      { label: "Cancel" },
      { label: "Change", primary: true, value: true },
    ],
  });
  if (!confirmed) return;
  const oldPw = $("cp-old").value;
  const newPw = $("cp-new").value;
  const confirmPw = $("cp-confirm").value;
  if (newPw !== confirmPw) {
    setStatus("New passwords do not match.", "error");
    return;
  }
  if (!newPw) {
    setStatus("New password must not be empty.", "error");
    return;
  }
  const res = await api("POST", "/v1/password", {
    body: { old_password: oldPw, new_password: newPw },
  });
  if (res.status !== 200) {
    const err = await safeError(res);
    setStatus("Password change failed: " + err, "error");
    return;
  }
  setStatus("Master password changed.", "ok");
}

/* ------------------------------------------------------------ export */
async function exportVault() {
  const res = await api("GET", "/v1/export");
  if (res.status !== 200) {
    setStatus("Export failed: " + (await safeError(res)), "error");
    return;
  }
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") || "";
  const m = disposition.match(/filename="?([^";]+)"?/);
  const filename = m ? m[1] : "apikey-vault.db";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  setStatus(`Exported encrypted vault (${filename}). Safe to move between devices.`, "ok");
}

/* ------------------------------------------------------------ import */
async function importVault(file) {
  if (!file) return;
  const confirmed = await showModal({
    title: "Import vault",
    body: `<p>Replace the current vault with <strong></strong>? The vault will be locked afterwards.</p>`,
    bodyName: file.name,
    actions: [
      { label: "Cancel" },
      { label: "Import", danger: true, value: true },
    ],
  });
  if (!confirmed) return;
  const bytes = await file.arrayBuffer();
  const res = await api("POST", "/v1/import", { raw: bytes });
  if (res.status !== 200) {
    setStatus("Import failed: " + (await safeError(res)), "error");
    return;
  }
  sessionStorage.removeItem("apivault_token");
  state.token = null;
  setLocked(true);
  setStatus("Vault imported — unlock with its master password.", "ok");
}

/* -------------------------------------------------------------- modal */
function showModal({ title, body, bodyName, actions }) {
  return new Promise((resolve) => {
    const backdrop = $("modal-backdrop");
    $("modal-title").textContent = title;
    $("modal-body").innerHTML = body;
    if (bodyName) {
      $("modal-body").querySelectorAll("strong").forEach((el) => {
        el.textContent = bodyName;
      });
    }
    const actionsEl = $("modal-actions");
    actionsEl.textContent = "";
    let result = false;
    const close = (val) => {
      backdrop.hidden = true;
      resolve(val);
    };
    for (const action of actions) {
      const btn = document.createElement("button");
      btn.textContent = action.label;
      if (action.primary) btn.className = "primary";
      if (action.danger) btn.className = "danger";
      btn.addEventListener("click", () => close(Boolean(action.value)));
      actionsEl.appendChild(btn);
    }
    backdrop.hidden = false;
    const first = $("modal-body").querySelector("input");
    if (first) first.focus();
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) close(false);
    });
  });
}

/* ------------------------------------------------------------ init flow */
async function onInit(e) {
  e.preventDefault();
  const pw = $("init-password").value;
  const confirm = $("init-confirm").value;
  $("init-error").hidden = true;
  if (!pw) {
    $("init-error").textContent = "Password must not be empty.";
    $("init-error").hidden = false;
    return;
  }
  if (pw !== confirm) {
    $("init-error").textContent = "Passwords do not match.";
    $("init-error").hidden = false;
    return;
  }
  const res = await api("POST", "/v1/init", { body: { password: pw }, noAuthReset: true });
  if (res.status !== 201) {
    $("init-error").textContent = "Failed to create vault: " + (await safeError(res));
    $("init-error").hidden = false;
    return;
  }
  const u = await api("POST", "/v1/unlock", { body: { password: pw }, noAuthReset: true });
  if (u.status === 200) {
    const d = await u.json();
    state.token = d.token;
    sessionStorage.setItem("apivault_token", d.token);
  }
  setLocked(false);
  setStatus("Vault created and unlocked.", "ok");
}

/* --------------------------------------------------------- unlock flows */
async function onUnlock(e) {
  e.preventDefault();
  const password = $("unlock-password").value;
  if (!password) return;
  $("unlock-error").hidden = true;
  const res = await api("POST", "/v1/unlock", {
    body: { password },
    noAuthReset: true,
  });
  if (res.status !== 200) {
    const data = await safeError(res);
    $("unlock-error").textContent =
      res.status === 401 ? "Invalid password." : "Unlock failed: " + data;
    $("unlock-error").hidden = false;
    return;
  }
  const data = await res.json();
  state.token = data.token;
  sessionStorage.setItem("apivault_token", data.token);
  setLocked(false);
}

async function onTokenConnect(e) {
  e.preventDefault();
  const token = $("token-input").value.trim();
  if (!token) return;
  state.token = token;
  const { status } = await apiJson("GET", "/v1/keys", { noAuthReset: false });
  if (status === 200) {
    sessionStorage.setItem("apivault_token", token);
    $("token-input").value = "";
    $("unlock-error").hidden = true;
    setLocked(false);
  } else if (status === 423) {
    $("unlock-error").textContent = "Vault is locked on the server — unlock with the master password first.";
    $("unlock-error").hidden = false;
    state.token = null;
  } else {
    $("unlock-error").textContent = "Invalid token.";
    $("unlock-error").hidden = false;
    state.token = null;
  }
}

async function onLock() {
  await api("POST", "/v1/lock", { noAuthReset: true });
  sessionStorage.removeItem("apivault_token");
  state.token = null;
  setLocked(true);
  setStatus("Vault locked.");
}

/* -------------------------------------------------------------- init */
async function init() {
  const res = await fetch("/v1/health");
  if (res.ok) {
    const health = await res.json();
    $("vault-path").textContent = health.initialized ? "local vault" : "not initialized";
    if (!health.initialized) {
      showScreen("init");
      $("init-password").focus();
      return;
    }
  }

  // try to resume an existing token for this tab session
  const saved = sessionStorage.getItem("apivault_token");
  if (saved) {
    state.token = saved;
    const { status } = await apiJson("GET", "/v1/keys");
    if (status === 200) {
      setLocked(false);
      return;
    }
    // token invalid/expired; api() already cleared it on 401
  }
  setLocked(true);
}

/* --------------------------------------------------------- wire up */
function wire() {
  $("init-form").addEventListener("submit", onInit);
  $("unlock-form").addEventListener("submit", onUnlock);
  $("token-form").addEventListener("submit", onTokenConnect);
  $("token-mode-btn").addEventListener("click", () => {
    $("token-form").hidden = !$("token-form").hidden;
    $("token-mode-btn").textContent = $("token-form").hidden
      ? "Use a bearer token instead"
      : "Use the master password";
    if (!$("token-form").hidden) $("token-input").focus();
  });
  $("lock-btn").addEventListener("click", onLock);
  $("add-key-btn").addEventListener("click", () => {
    state.selected = null;
    renderList();
    openEditor("add", null);
  });
  $("editor-form").addEventListener("submit", onEditorSave);
  $("editor-cancel").addEventListener("click", () => {
    if (state.selected) selectKey(state.selected);
    else showEmptyDetail();
  });
  $("paste-save").addEventListener("click", onPasteSave);
  $("paste-clear").addEventListener("click", () => {
    $("paste-input").value = "";
    $("paste-name").value = "";
    $("paste-status").textContent = "";
  });
  $("paste-input").addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") onPasteSave();
  });
  $("copy-btn").addEventListener("click", copyValue);
  $("copy-plain-btn").addEventListener("click", copyPlaintext);
  $("reveal-btn").addEventListener("click", () => revealValue());
  $("reveal-inline").addEventListener("click", () => revealValue());
  $("delete-btn").addEventListener("click", deleteSelected);
  $("rename-btn").addEventListener("click", () => {
    const key = state.keys.find((k) => k.name === state.selected);
    if (key) openEditor("rename", key);
  });
  $("change-pw-btn").addEventListener("click", changePassword);
  $("export-btn").addEventListener("click", exportVault);
  $("import-btn").addEventListener("click", () => $("import-file").click());
  $("import-file").addEventListener("change", (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (file) importVault(file);
  });
  $("key-filter").addEventListener("input", (e) => {
    state.filter = e.target.value;
    renderList();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const backdrop = $("modal-backdrop");
      if (!backdrop.hidden) backdrop.hidden = true;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  wire();
  init();
});

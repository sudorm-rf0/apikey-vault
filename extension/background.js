// Service worker: resolves a detected key value to a vault key name when the
// user has enabled vault integration (options page). Uses the extension's own
// origin so it is not subject to page CORS.

const API_ROOT = "http://127.0.0.1:8417";
let cache = { names: null, at: 0 };

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "guard:resolve") {
    resolveKey(msg.value)
      .then((name) => sendResponse({ name }))
      .catch(() => sendResponse({ name: null }));
    return true; // async response
  }
});

async function resolveKey(value) {
  const settings = await chrome.storage.sync.get({
    vaultEnabled: false,
    vaultToken: "",
  });
  if (!settings.vaultEnabled) return null;

  const names = await listNames(settings.vaultToken);
  for (const name of names) {
    const stored = await getValue(name, settings.vaultToken);
    if (stored === value) return name;
  }
  return null;
}

async function listNames(token) {
  const res = await fetch(`${API_ROOT}/v1/keys`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`list keys failed: ${res.status}`);
  const data = await res.json();
  return (data.keys || []).map((k) => k.name);
}

async function getValue(name, token) {
  const res = await fetch(
    `${API_ROOT}/v1/keys/${encodeURIComponent(name)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  );
  if (!res.ok) return null;
  const data = await res.json();
  return data.value;
}

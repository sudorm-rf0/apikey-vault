// Service worker: resolves a detected key value to a vault key name when the
// user has enabled vault integration (options page). Uses the extension's own
// origin so it is not subject to page CORS.

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "guard:resolve") {
    resolveKey(msg.value)
      .then((name) => sendResponse({ name }))
      .catch(() => sendResponse({ name: null }));
    return true; // async response
  }
});

async function settings() {
  return chrome.storage.sync.get({
    vaultEnabled: false,
    vaultToken: "",
    vaultUrl: "http://127.0.0.1:8417",
  });
}

async function resolveKey(value) {
  const cfg = await settings();
  if (!cfg.vaultEnabled) return null;

  const names = await listNames(cfg);
  for (const name of names) {
    const stored = await getValue(name, cfg);
    if (stored === value) return name;
  }
  return null;
}

function apiRoot(cfg) {
  return cfg.vaultUrl.replace(/\/$/, "");
}

async function listNames(cfg) {
  const res = await fetch(`${apiRoot(cfg)}/v1/keys`, {
    headers: cfg.vaultToken ? { Authorization: `Bearer ${cfg.vaultToken}` } : {},
  });
  if (!res.ok) throw new Error(`list keys failed: ${res.status}`);
  const data = await res.json();
  return (data.keys || []).map((k) => k.name);
}

async function getValue(name, cfg) {
  const res = await fetch(`${apiRoot(cfg)}/v1/keys/${encodeURIComponent(name)}`, {
    headers: cfg.vaultToken ? { Authorization: `Bearer ${cfg.vaultToken}` } : {},
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.value;
}

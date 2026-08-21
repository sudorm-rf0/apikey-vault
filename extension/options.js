const $ = (id) => document.getElementById(id);

chrome.storage.sync.get({ vaultEnabled: false, vaultToken: "", vaultUrl: "http://127.0.0.1:8417" }, (s) => {
  $("vaultEnabled").checked = s.vaultEnabled;
  $("vaultToken").value = s.vaultToken;
  $("vaultUrl").value = s.vaultUrl;
});

$("save").addEventListener("click", () => {
  let url = $("vaultUrl").value.trim().replace(/\/$/, "");
  if (!url) url = "http://127.0.0.1:8417";
  chrome.storage.sync.set({
    vaultEnabled: $("vaultEnabled").checked,
    vaultToken: $("vaultToken").value.trim(),
    vaultUrl: url,
  }, () => {
    $("status").textContent = "Saved. Redaction is active on all pages.";
    setTimeout(() => ($("status").textContent = ""), 3000);
  });
});

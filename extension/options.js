const $ = (id) => document.getElementById(id);

chrome.storage.sync.get({ vaultEnabled: false, vaultToken: "" }, (s) => {
  $("vaultEnabled").checked = s.vaultEnabled;
  $("vaultToken").value = s.vaultToken;
});

$("save").addEventListener("click", () => {
  chrome.storage.sync.set({
    vaultEnabled: $("vaultEnabled").checked,
    vaultToken: $("vaultToken").value.trim(),
  }, () => {
    $("status").textContent = "Saved. Redaction is active on all pages.";
    setTimeout(() => ($("status").textContent = ""), 3000);
  });
});

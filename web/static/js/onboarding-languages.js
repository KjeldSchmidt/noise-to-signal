(function () {
  const form = document.getElementById("onboarding-languages-form");
  if (!form || form.dataset.prefillFromBrowser !== "1") return;

  const catalog = (form.dataset.catalogLanguages || "")
    .split(",")
    .map(function (code) {
      return code.trim().toLowerCase();
    })
    .filter(Boolean);
  if (!catalog.length) return;

  const catalogSet = new Set(catalog);
  const browserLangs = Array.isArray(navigator.languages)
    ? navigator.languages.slice()
    : [navigator.language || "en"];

  const selected = [];
  let primary = "";
  browserLangs.forEach(function (raw) {
    if (!raw) return;
    const lower = String(raw).toLowerCase().replace("_", "-");
    const base = lower.split("-")[0];
    let match = "";
    if (catalogSet.has(lower)) match = lower;
    else if (catalogSet.has(base)) match = base;
    if (!match) return;
    if (selected.indexOf(match) === -1) selected.push(match);
    if (!primary) primary = match;
  });

  if (!selected.length) {
    selected.push(catalogSet.has("en") ? "en" : catalog[0]);
    primary = selected[0];
  }

  const langInputs = form.querySelectorAll('input[name="languages"]');
  langInputs.forEach(function (input) {
    input.checked = selected.indexOf(input.value) !== -1;
  });

  const primaryInputs = form.querySelectorAll('input[name="primary"]');
  let primarySet = false;
  primaryInputs.forEach(function (input) {
    const on = input.value === primary;
    input.checked = on;
    if (on) primarySet = true;
  });
  if (!primarySet && primaryInputs.length) {
    primaryInputs[0].checked = true;
  }
})();

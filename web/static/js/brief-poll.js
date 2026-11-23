(function () {
  var host = document.querySelector("[data-brief-status]");
  if (!host) return;
  var url = host.getAttribute("data-brief-status-url");
  if (!url) return;

  var attempts = 0;
  var maxAttempts = 90;
  var timer = null;

  function stop() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  function tick() {
    attempts += 1;
    if (attempts > maxAttempts) {
      stop();
      host.innerHTML =
        "<p><strong>Still working…</strong> Refresh the page in a minute if this does not update.</p>";
      return;
    }
    fetch(url, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (res) {
        if (!res.ok) throw new Error("status " + res.status);
        return res.json();
      })
      .then(function (data) {
        if (data.status === "ready") {
          stop();
          window.location.reload();
          return;
        }
        if (data.status === "failed") {
          stop();
          host.innerHTML =
            "<p><strong>Personalization failed.</strong> " +
            (data.error ? String(data.error) : "Showing interim stories — try refreshing later.") +
            "</p>";
        }
      })
      .catch(function () {
        /* keep polling */
      });
  }

  timer = setInterval(tick, 2000);
  tick();
})();

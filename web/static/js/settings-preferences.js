(function () {
  const openBtn = document.querySelector("[data-prefs-open]");
  const dialog = document.querySelector("[data-prefs-modal]");
  const body = document.querySelector("[data-prefs-body]");
  if (!openBtn || !dialog || !body) return;

  const listUrl = openBtn.getAttribute("data-list-url") || "";
  const deleteMemoryUrl = openBtn.getAttribute("data-delete-memory-url") || "";
  const deleteThemeUrl = openBtn.getAttribute("data-delete-theme-url") || "";
  const csrf = openBtn.getAttribute("data-csrf") || "";

  function setBodyHtml(html) {
    body.innerHTML = html;
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function render(data) {
    const memories = data.memories || [];
    const themes = data.themes || [];
    let html = "";

    html += "<h3 class=\"settings-subhead\">Memories</h3>";
    if (!memories.length) {
      html += "<p class=\"muted\">No free-form preference memories yet.</p>";
    } else {
      html += "<ul class=\"prefs-list\">";
      memories.forEach(function (row) {
        html +=
          "<li class=\"prefs-row\">" +
          "<span class=\"prefs-text\">" +
          escapeHtml(row.text || "") +
          "</span>" +
          "<button type=\"button\" class=\"linkish muted\" data-delete-memory=\"" +
          escapeHtml(row.id) +
          "\">delete</button>" +
          "</li>";
      });
      html += "</ul>";
    }

    html += "<h3 class=\"settings-subhead\">Theme leanings</h3>";
    if (!themes.length) {
      html += "<p class=\"muted\">No theme more/less counts yet.</p>";
    } else {
      html += "<ul class=\"prefs-list\">";
      themes.forEach(function (row) {
        html +=
          "<li class=\"prefs-row\">" +
          "<span class=\"prefs-text\">" +
          escapeHtml(row.label || row.slug) +
          ": more " +
          String(row.more_count || 0) +
          " / less " +
          String(row.less_count || 0) +
          "</span>" +
          "<button type=\"button\" class=\"linkish muted\" data-delete-theme=\"" +
          escapeHtml(row.slug) +
          "\">reset</button>" +
          "</li>";
      });
      html += "</ul>";
    }
    setBodyHtml(html);
  }

  function load() {
    setBodyHtml("<p class=\"muted\">Loading…</p>");
    return fetch(listUrl, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok || !data.ok) {
            throw new Error((data && data.error) || "Could not load preferences.");
          }
          render(data);
        });
      })
      .catch(function (err) {
        setBodyHtml(
          "<p class=\"muted\">" + escapeHtml(err.message || "Could not load preferences.") + "</p>"
        );
      });
  }

  function postDelete(url, field, value) {
    const bodyData = new FormData();
    bodyData.set(field, value);
    bodyData.set("csrfmiddlewaretoken", csrf);
    return fetch(url, {
      method: "POST",
      body: bodyData,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) {
          throw new Error((data && data.error) || "Delete failed.");
        }
      });
    });
  }

  openBtn.addEventListener("click", function () {
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    load();
  });

  body.addEventListener("click", function (event) {
    const memBtn = event.target.closest("[data-delete-memory]");
    if (memBtn) {
      const id = memBtn.getAttribute("data-delete-memory");
      if (!id) return;
      memBtn.disabled = true;
      postDelete(deleteMemoryUrl, "record_id", id)
        .then(load)
        .catch(function (err) {
          memBtn.disabled = false;
          window.alert(err.message || "Delete failed.");
        });
      return;
    }
    const themeBtn = event.target.closest("[data-delete-theme]");
    if (themeBtn) {
      const slug = themeBtn.getAttribute("data-delete-theme");
      if (!slug) return;
      themeBtn.disabled = true;
      postDelete(deleteThemeUrl, "theme", slug)
        .then(load)
        .catch(function (err) {
          themeBtn.disabled = false;
          window.alert(err.message || "Reset failed.");
        });
    }
  });
})();

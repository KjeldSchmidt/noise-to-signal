(function () {
  const list = document.querySelector("[data-brief-list]");
  if (!list) return;

  const toastHost = document.querySelector("[data-brief-toast]");
  const emptyTemplate = document.getElementById("brief-empty-template");
  const STORAGE_PREFIX = "n2s:theme-affinity:";

  function showToast(text, isError) {
    if (!toastHost || !text) return;
    const el = document.createElement("div");
    el.className = "brief-toast" + (isError ? " error" : "");
    el.textContent = text;
    toastHost.replaceChildren(el);
    window.clearTimeout(showToast._timer);
    showToast._timer = window.setTimeout(function () {
      el.remove();
    }, 2200);
  }

  function showEmptyState() {
    if (!emptyTemplate || !emptyTemplate.content) return;
    const empty = emptyTemplate.content.firstElementChild.cloneNode(true);
    list.replaceWith(empty);
  }

  function removeItem(item) {
    let finished = false;
    const done = function () {
      if (finished) return;
      finished = true;
      item.remove();
      if (!list.querySelector(".item")) {
        showEmptyState();
      }
    };
    item.classList.add("is-leaving");
    item.addEventListener("transitionend", done, { once: true });
    window.setTimeout(done, 280);
  }

  function postForm(form, extra) {
    const body = new FormData(form);
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        body.set(key, extra[key]);
      });
    }
    return fetch(form.action, {
      method: "POST",
      body: body,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok && data.ok, data: data };
      });
    });
  }

  function storageKey(articleId, themeSlug) {
    return STORAGE_PREFIX + articleId + ":" + themeSlug;
  }

  function readLean(articleId, themeSlug) {
    try {
      const value = window.localStorage.getItem(storageKey(articleId, themeSlug));
      if (value === "more" || value === "less") return value;
    } catch (_err) {
      /* ignore quota / private mode */
    }
    return "neutral";
  }

  function writeLean(articleId, themeSlug, direction) {
    try {
      window.localStorage.setItem(storageKey(articleId, themeSlug), direction);
    } catch (_err) {
      /* ignore quota / private mode */
    }
  }

  function applyLeanUi(form, lean) {
    const previousInput = form.querySelector(".theme-chip-previous");
    if (previousInput) previousInput.value = lean === "neutral" ? "neutral" : lean;
    form.querySelectorAll("button[name='direction']").forEach(function (btn) {
      const selected = lean !== "neutral" && btn.value === lean;
      btn.classList.toggle("is-selected", selected);
      btn.disabled = selected;
      btn.setAttribute("aria-pressed", selected ? "true" : "false");
    });
  }

  function initThemeChips() {
    list.querySelectorAll("form.theme-chip-form").forEach(function (form) {
      const articleId = form.dataset.articleId;
      const themeSlug = form.dataset.themeSlug;
      if (!articleId || !themeSlug) return;
      applyLeanUi(form, readLean(articleId, themeSlug));
    });
  }

  initThemeChips();

  list.addEventListener("click", function (event) {
    const themeBtn = event.target.closest("button[name='direction']");
    if (themeBtn) {
      const form = themeBtn.closest("form.theme-chip-form");
      if (!form) return;
      event.preventDefault();
      const articleId = form.dataset.articleId;
      const themeSlug = form.dataset.themeSlug;
      if (!articleId || !themeSlug) return;

      const previous = readLean(articleId, themeSlug);
      const direction = themeBtn.value;
      if (previous === direction) return;
      if (form.dataset.busy === "1") return;

      form.dataset.busy = "1";
      form.querySelectorAll("button").forEach(function (btn) {
        btn.disabled = true;
      });
      postForm(form, { direction: direction, previous: previous })
        .then(function (result) {
          if (!result.ok) {
            throw new Error((result.data && result.data.error) || "Could not save preference.");
          }
          writeLean(articleId, themeSlug, direction);
          applyLeanUi(form, direction);
          form.dataset.busy = "0";
          showToast(result.data.message);
        })
        .catch(function (err) {
          form.dataset.busy = "0";
          applyLeanUi(form, previous);
          showToast(err.message || "Could not save preference.", true);
        });
      return;
    }

    const button = event.target.closest("button[name='verdict']");
    if (!button) return;
    const form = button.closest("form.feedback-row");
    const item = button.closest(".item");
    if (!form || !item) return;

    event.preventDefault();
    if (form.dataset.busy === "1") return;
    form.dataset.busy = "1";
    form.querySelectorAll("button").forEach(function (btn) {
      btn.disabled = true;
    });

    postForm(form, { verdict: button.value })
      .then(function (result) {
        if (!result.ok) {
          throw new Error((result.data && result.data.error) || "Could not save feedback.");
        }
        showToast(result.data.message);
        removeItem(item);
      })
      .catch(function (err) {
        form.dataset.busy = "0";
        form.querySelectorAll("button").forEach(function (btn) {
          btn.disabled = false;
        });
        showToast(err.message || "Could not save feedback.", true);
      });
  });
})();

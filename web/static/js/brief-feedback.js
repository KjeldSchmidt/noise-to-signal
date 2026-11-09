(function () {
  const list = document.querySelector("[data-brief-list]");
  if (!list) return;

  const toastHost = document.querySelector("[data-brief-toast]");
  const emptyTemplate = document.getElementById("brief-empty-template");

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

  list.addEventListener("click", function (event) {
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

    const body = new FormData(form);
    body.set("verdict", button.value);

    fetch(form.action, {
      method: "POST",
      body: body,
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok && data.ok, data: data };
        });
      })
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

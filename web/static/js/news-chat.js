(function () {
  const root = document.querySelector("[data-news-chat]");
  if (!root || root.dataset.bound === "1") return;
  root.dataset.bound = "1";

  const form = root.querySelector("[data-chat-form]");
  const input = root.querySelector("[data-chat-input]");
  const messages = root.querySelector("[data-chat-messages]");
  const empty = root.querySelector("[data-chat-empty]");
  const status = root.querySelector("[data-chat-status]");
  const sendBtn = root.querySelector("[data-chat-send]");
  if (!form || !input || !messages || !sendBtn) return;

  const url = root.dataset.chatUrl;
  const scope = root.dataset.chatScope;
  const scopeId = root.dataset.chatScopeId || null;
  const csrfInput = form.querySelector("input[name='csrfmiddlewaretoken']");
  const history = [];
  const MAX_HISTORY = 12;

  function setStatus(text, isError) {
    if (!status) return;
    if (!text) {
      status.hidden = true;
      status.textContent = "";
      status.classList.remove("is-error");
      return;
    }
    status.hidden = false;
    status.textContent = text;
    status.classList.toggle("is-error", !!isError);
  }

  function appendBubble(role, text) {
    if (empty) empty.remove();
    const el = document.createElement("div");
    el.className = "news-chat-bubble is-" + role;
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  function resizeInput() {
    input.style.height = "auto";
    const max = Number.parseFloat(window.getComputedStyle(input).maxHeight) || 160;
    const next = Math.min(input.scrollHeight, max);
    input.style.height = next + "px";
    input.style.overflowY = input.scrollHeight > max ? "auto" : "hidden";
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    form.dataset.busy = busy ? "1" : "0";
  }

  function submitChat() {
    if (form.dataset.busy === "1") return;
    const message = (input.value || "").trim();
    if (!message) return;

    setStatus("");
    appendBubble("user", message);
    input.value = "";
    resizeInput();
    setBusy(true);
    setStatus("Thinking…");
    input.focus();

    const body = {
      scope: scope,
      message: message,
      history: history.slice(-MAX_HISTORY),
    };
    if (scopeId) body.scope_id = Number(scopeId);

    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfInput ? csrfInput.value : "",
      },
      body: JSON.stringify(body),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, status: response.status, data: data };
        });
      })
      .then(function (result) {
        setBusy(false);
        setStatus("");
        input.focus();
        if (result.status === 429) {
          setStatus(
            (result.data && result.data.error) ||
              "Rate limit reached. Try again in a minute.",
            true
          );
          return;
        }
        if (!result.ok || !result.data || !result.data.ok) {
          throw new Error(
            (result.data && result.data.error) || "Chat request failed."
          );
        }
        const reply = result.data.reply || "";
        appendBubble(result.data.refused ? "refuse" : "assistant", reply);
        history.push({ role: "user", content: message });
        if (!result.data.refused && reply) {
          history.push({ role: "assistant", content: reply });
        }
        while (history.length > MAX_HISTORY) history.shift();
      })
      .catch(function (err) {
        setBusy(false);
        setStatus(err.message || "Chat request failed.", true);
        input.focus();
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submitChat();
  });

  input.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") return;
    if (event.shiftKey) return;
    if (event.isComposing) return;
    event.preventDefault();
    submitChat();
  });

  input.addEventListener("input", resizeInput);
  resizeInput();
})();

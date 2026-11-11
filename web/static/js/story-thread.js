(() => {
  const root = document.getElementById("thread-timeline");
  if (!root) return;

  const items = Array.from(root.querySelectorAll("[data-timeline-item]"));

  function selectItem(item) {
    items.forEach((other) => {
      const selected = other === item;
      other.classList.toggle("is-selected", selected);
      other.classList.toggle("is-collapsed", !selected && other.classList.contains("is-newest"));
      const toggle = other.querySelector("[data-timeline-toggle]");
      if (toggle) toggle.setAttribute("aria-expanded", selected ? "true" : "false");
    });
  }

  items.forEach((item) => {
    const toggle = item.querySelector("[data-timeline-toggle]");
    if (!toggle) return;

    const activate = (event) => {
      if (event.target.closest("[data-external-link]")) return;
      selectItem(item);
    };

    toggle.addEventListener("click", activate);
    toggle.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest("[data-external-link]")) return;
      event.preventDefault();
      selectItem(item);
    });
  });
})();

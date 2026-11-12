(() => {
  const root = document.getElementById("thread-timeline");
  if (!root) return;

  /**
   * @param {HTMLElement} foldout
   * @returns {{ clip: HTMLElement, copy: HTMLElement, toggle: HTMLButtonElement } | null}
   */
  function parts(foldout) {
    const clip = foldout.querySelector(".timeline-summary-clip");
    const copy = foldout.querySelector(".timeline-summary-copy");
    const toggle = foldout.querySelector(".timeline-summary-toggle");
    if (
      !(clip instanceof HTMLElement) ||
      !(copy instanceof HTMLElement) ||
      !(toggle instanceof HTMLButtonElement)
    ) {
      return null;
    }
    return { clip, copy, toggle };
  }

  /**
   * @param {HTMLElement} el
   * @returns {number}
   */
  function lineHeightPx(el) {
    const raw = getComputedStyle(el).lineHeight;
    const parsed = Number.parseFloat(raw);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
    const fontSize = Number.parseFloat(getComputedStyle(el).fontSize);
    return Number.isFinite(fontSize) ? fontSize * 1.45 : 20;
  }

  /**
   * @param {HTMLElement} clip
   * @param {HTMLElement} copy
   * @returns {boolean}
   */
  function overflowsOneLine(clip, copy) {
    const width = clip.getBoundingClientRect().width;
    if (width <= 0) return true;

    const style = getComputedStyle(copy);
    const probe = document.createElement("div");
    probe.textContent = copy.textContent ?? "";
    probe.style.cssText = [
      "position:absolute",
      "visibility:hidden",
      "pointer-events:none",
      "left:0",
      "top:0",
      `width:${width}px`,
      `font:${style.font}`,
      `line-height:${style.lineHeight}`,
      `letter-spacing:${style.letterSpacing}`,
      `word-spacing:${style.wordSpacing}`,
      "white-space:normal",
    ].join(";");
    document.body.appendChild(probe);
    const fullHeight = probe.scrollHeight;
    const oneLine = lineHeightPx(probe);
    probe.remove();
    return fullHeight > oneLine + 1;
  }

  /**
   * @param {HTMLElement} foldout
   */
  function syncToggle(foldout) {
    const p = parts(foldout);
    if (!p) return;
    const expanded = foldout.classList.contains("is-expanded");
    const short = foldout.classList.contains("is-short");
    p.toggle.disabled = short;
    p.toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  }

  /**
   * @param {HTMLElement} foldout
   */
  function markIfShort(foldout) {
    if (foldout.classList.contains("is-animating")) return;
    const p = parts(foldout);
    if (!p) return;

    const wasExpanded = foldout.classList.contains("is-expanded");
    const overflows = overflowsOneLine(p.clip, p.copy);
    foldout.classList.toggle("is-short", !overflows);
    foldout.classList.toggle("is-expanded", wasExpanded || !overflows);
    p.clip.style.height = "";
    syncToggle(foldout);
  }

  /**
   * @param {HTMLElement} clip
   * @param {() => void} done
   */
  function afterHeightTransition(clip, done) {
    let settled = false;
    const settle = () => {
      if (settled) return;
      settled = true;
      clip.removeEventListener("transitionend", onEnd);
      window.clearTimeout(fallback);
      done();
    };
    /** @param {TransitionEvent} event */
    const onEnd = (event) => {
      if (event.target !== clip || event.propertyName !== "height") return;
      settle();
    };
    clip.addEventListener("transitionend", onEnd);
    const fallback = window.setTimeout(settle, 350);
  }

  /**
   * @param {HTMLElement} foldout
   * @param {boolean} expanded
   */
  function animateFoldout(foldout, expanded) {
    const p = parts(foldout);
    if (!p || foldout.classList.contains("is-animating")) return;
    if (foldout.classList.contains("is-expanded") === expanded) return;

    const start = p.clip.getBoundingClientRect().height;
    // Suppress line-clamp / CSS height:auto while we drive px heights inline.
    foldout.classList.add("is-animating");
    p.clip.style.height = `${start}px`;
    void p.clip.offsetHeight;

    /** @type {number} */
    let end;
    if (expanded) {
      p.clip.style.height = "auto";
      end = p.clip.scrollHeight;
      p.clip.style.height = `${start}px`;
      void p.clip.offsetHeight;
      foldout.classList.add("is-expanded");
    } else {
      foldout.classList.remove("is-expanded");
      end = lineHeightPx(p.copy);
    }

    syncToggle(foldout);
    afterHeightTransition(p.clip, () => {
      foldout.classList.remove("is-animating");
      p.clip.style.height = "";
      syncToggle(foldout);
    });

    p.clip.style.height = `${end}px`;
  }

  /**
   * @param {HTMLElement} foldout
   */
  function toggleFoldout(foldout) {
    if (foldout.classList.contains("is-short")) return;
    animateFoldout(foldout, !foldout.classList.contains("is-expanded"));
  }

  /**
   * Cap media to the lede block height (tag + title + time + padding).
   * Width follows natural aspect ratio within max-width; never drives row height.
   * @param {HTMLElement} card
   */
  function syncCardMedia(card) {
    const media = card.querySelector(".timeline-media");
    const img = media instanceof HTMLElement ? media.querySelector("img") : null;
    const lede = card.querySelector("[data-timeline-lede]");
    if (
      !(media instanceof HTMLElement) ||
      !(img instanceof HTMLImageElement) ||
      !(lede instanceof HTMLElement)
    ) {
      return;
    }

    const apply = () => {
      const maxHeight = lede.offsetHeight;
      if (maxHeight <= 0) return;

      const rootFont = Number.parseFloat(
        getComputedStyle(document.documentElement).fontSize,
      );
      const maxWidth = Math.min(card.clientWidth * 0.42, rootFont * 14);

      const nw = img.naturalWidth;
      const nh = img.naturalHeight;
      let height = maxHeight;
      let width = maxHeight;
      if (nw > 0 && nh > 0) {
        width = height * (nw / nh);
        if (width > maxWidth) {
          width = maxWidth;
          height = width * (nh / nw);
        }
      } else {
        width = Math.min(maxHeight, maxWidth);
      }

      media.style.height = `${height}px`;
      media.style.width = `${width}px`;
    };

    apply();
    // Title may wrap after media takes width; remeasure lede (image stays ≤ lede height).
    requestAnimationFrame(apply);
    if (!img.complete || img.naturalWidth === 0) {
      img.addEventListener(
        "load",
        () => {
          apply();
          requestAnimationFrame(apply);
        },
        { once: true },
      );
    }
  }

  const foldouts = Array.from(
    root.querySelectorAll("[data-summary-foldout]"),
  ).filter((node) => node instanceof HTMLElement);

  const imageCards = Array.from(
    root.querySelectorAll(".timeline-card.has-image"),
  ).filter((node) => node instanceof HTMLElement);

  foldouts.forEach((foldout) => {
    markIfShort(foldout);
    const p = parts(foldout);
    if (!p) return;
    p.toggle.addEventListener("click", () => toggleFoldout(foldout));
  });

  imageCards.forEach(syncCardMedia);

  let resizeTimer = 0;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      foldouts.forEach(markIfShort);
      imageCards.forEach(syncCardMedia);
    }, 150);
  });
})();

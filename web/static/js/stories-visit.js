(() => {
  const STORAGE_KEY = "n2s_stories_last_visit";
  const SESSION_KEY = "n2s_stories_visit_active";

  function readLastVisit() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  }

  function writeLastVisit(iso) {
    try {
      window.localStorage.setItem(STORAGE_KEY, iso);
    } catch {
      /* ignore quota / private mode */
    }
  }

  function ensureSinceInUrl() {
    const params = new URLSearchParams(window.location.search);
    if (params.has("since")) {
      return false;
    }
    const since = readLastVisit();
    if (!since) {
      return false;
    }
    params.set("since", since);
    const next = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
    window.location.replace(next);
    return true;
  }

  function markSessionAndScheduleWatermark() {
    try {
      if (!window.sessionStorage.getItem(SESSION_KEY)) {
        window.sessionStorage.setItem(SESSION_KEY, "1");
      }
    } catch {
      /* ignore */
    }

    const persist = () => {
      writeLastVisit(new Date().toISOString());
    };

    window.addEventListener("pagehide", persist);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") {
        persist();
      }
    });
  }

  // Avoid advancing the watermark on the brief redirect hop that injects ?since=.
  if (!ensureSinceInUrl()) {
    markSessionAndScheduleWatermark();
  }
})();

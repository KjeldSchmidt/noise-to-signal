(function () {
  const form = document.getElementById("location-picker-form");
  if (!form) return;

  const reverseUrl = form.dataset.reverseUrl;
  const searchUrl = form.dataset.searchUrl;
  const labelInput = document.getElementById("id_location_label");
  const latInput = document.getElementById("id_location_lat");
  const lngInput = document.getElementById("id_location_lng");
  const searchInput = document.getElementById("location-search");
  const suggestions = document.getElementById("location-suggestions");
  const status = document.getElementById("geo-status");
  const useBtn = document.getElementById("use-my-location");
  const addBtn = document.getElementById("add-location-btn");

  let searchTimer = null;
  let reverseAbort = null;

  const preferLang = (navigator.languages && navigator.languages[0]) || navigator.language || "en";

  function withLang(url) {
    const sep = url.indexOf("?") >= 0 ? "&" : "?";
    return url + sep + "lang=" + encodeURIComponent(preferLang);
  }

  function setStatus(text) {
    if (!status) return;
    const msg = text || "";
    status.textContent = msg;
    status.hidden = !msg;
  }

  let placeCommitted = false;

  function syncAddEnabled() {
    if (!addBtn) return;
    const hasLabel = labelInput && labelInput.value.trim().length > 0;
    const hasCoords = latInput && lngInput && latInput.value && lngInput.value;
    addBtn.disabled = !(placeCommitted && hasLabel && hasCoords);
  }

  function clearSelection() {
    placeCommitted = false;
    if (labelInput) labelInput.value = "";
    if (latInput) latInput.value = "";
    if (lngInput) lngInput.value = "";
    syncAddEnabled();
  }

  function selectPlace(hit) {
    placeCommitted = true;
    if (labelInput) labelInput.value = hit.label || "";
    if (latInput) latInput.value = hit.latitude != null ? String(hit.latitude) : "";
    if (lngInput) lngInput.value = hit.longitude != null ? String(hit.longitude) : "";
    if (searchInput) searchInput.value = hit.label || "";
    syncAddEnabled();
  }

  function hideSuggestions() {
    if (!suggestions) return;
    suggestions.hidden = true;
    suggestions.innerHTML = "";
  }

  function showSuggestions(results) {
    if (!suggestions) return;
    suggestions.innerHTML = "";
    if (!results.length) {
      hideSuggestions();
      return;
    }
    results.forEach(function (hit) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = hit.label;
      btn.addEventListener("click", function () {
        hideSuggestions();
        selectPlace(hit);
      });
      li.appendChild(btn);
      suggestions.appendChild(li);
    });
    suggestions.hidden = false;
  }

  if (searchInput) {
    searchInput.addEventListener("input", function () {
      // Typing means the previous pick is no longer authoritative.
      clearSelection();
      const q = searchInput.value.trim();
      clearTimeout(searchTimer);
      if (q.length < 2) {
        hideSuggestions();
        return;
      }
      searchTimer = setTimeout(function () {
        fetch(withLang(searchUrl + "?q=" + encodeURIComponent(q)), {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        })
          .then(function (res) {
            if (!res.ok) throw new Error("search failed");
            return res.json();
          })
          .then(function (data) {
            showSuggestions(data.results || []);
          })
          .catch(function () {
            hideSuggestions();
          });
      }, 350);
    });

    document.addEventListener("click", function (e) {
      if (!suggestions || suggestions.hidden) return;
      if (form.contains(e.target)) return;
      hideSuggestions();
    });
  }

  if (useBtn) {
    useBtn.addEventListener("click", function () {
      if (!navigator.geolocation) {
        setStatus("Geolocation is not supported in this browser.");
        return;
      }
      setStatus("Waiting for permission…");
      useBtn.disabled = true;
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;
          if (reverseAbort) reverseAbort.abort();
          reverseAbort = new AbortController();
          setStatus("Looking up place name…");
          fetch(
            withLang(
              reverseUrl +
                "?lat=" +
                encodeURIComponent(lat) +
                "&lng=" +
                encodeURIComponent(lng)
            ),
            {
              credentials: "same-origin",
              headers: { Accept: "application/json" },
              signal: reverseAbort.signal,
            }
          )
            .then(function (res) {
              if (!res.ok) throw new Error("reverse failed");
              return res.json();
            })
            .then(function (data) {
              useBtn.disabled = false;
              setStatus("");
              selectPlace({
                label: data.label,
                latitude: data.latitude,
                longitude: data.longitude,
              });
            })
            .catch(function (err) {
              useBtn.disabled = false;
              if (err && err.name === "AbortError") return;
              setStatus("Could not resolve place name.");
              selectPlace({
                label:
                  "Near " + Number(lat).toFixed(2) + ", " + Number(lng).toFixed(2),
                latitude: lat,
                longitude: lng,
              });
            });
        },
        function (err) {
          useBtn.disabled = false;
          if (err.code === err.PERMISSION_DENIED) {
            setStatus("Location permission denied — search for a place instead.");
          } else {
            setStatus("Could not read location — search for a place instead.");
          }
        },
        { enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 }
      );
    });
  }

  syncAddEnabled();
})();

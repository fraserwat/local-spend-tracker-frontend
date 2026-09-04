document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("map");
  const statusEl = document.getElementById("status");
  const badgeEl = document.getElementById("coverage-badge");
  const nationNoteEl = document.getElementById("nation-note");
  const geojsonUrl = mapEl.dataset.geojsonUrl;
  const manifestUrl = mapEl.dataset.manifestUrl;
  const nationsUrl = mapEl.dataset.nationsUrl;
  const initialSelectedSlug = mapEl.dataset.selectedSlug || null;

  // No equivalent of England's Transparency Code in these nations, so no
  // comparable itemised spend data. Static copy, not model-backed.
  const NATION_NOTES = {
    scotland:
      "Scotland has no equivalent of England's Local Government " +
      "Transparency Code 2015 -- itemised spend disclosure is voluntary. " +
      "Of 32 councils surveyed, only 6 publish anything close to " +
      "transaction-level data, at inconsistent thresholds and via " +
      "inconsistent channels.",
    wales:
      "Wales has no equivalent of England's Local Government Transparency " +
      "Code 2015 either. Of 22 councils surveyed, only 3 publish a " +
      "spend-over-£500 register -- one council's own FOI response " +
      "confirmed Welsh authorities aren't required to.",
    "northern-ireland":
      "Northern Ireland has no equivalent statutory duty to publish " +
      "itemised spend. All 11 district councils were surveyed and none " +
      "publish a spend-over-£500 register, so it's out of scope entirely.",
  };

  // Closure state read by the selected layer's own event handlers, so a
  // switch just reassigns these instead of rebuilding every handler.
  let selectedSlugState = null;
  let selectedLayer = null;
  let coveragePromise = Promise.resolve(null);

  // Bumped on every renderSelectedCouncil()/showIdleState() call; a stale
  // async callback compares against this before touching selectedLayer/
  // selectedSlugState/the camera, so a slow-resolving earlier switch can't
  // clobber a faster later one.
  let renderGeneration = 0;

  // slug -> parsed GeoJSON, populated on first fetch and never evicted, so
  // re-selecting a council is a zero-network layer rebuild.
  const boundaryCache = new Map();
  // slug -> idle-styled layer currently on the map. Never has the selected
  // council's slug as a key -- removed on promotion, re-added on demotion.
  const idleLayersBySlug = new Map();
  // slug -> manifest entry, so a switch can look up any council's boundary
  // file without a second manifest fetch.
  let manifestEntriesBySlug = null;
  let manifestBaseUrl = "";

  const prefersReducedMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Darker + more opaque than before so idle councils read as clickable.
  const IDLE_STYLE = { color: "#6b6e87", weight: 2, fillOpacity: 0.14, dashArray: "4 4" };
  // Fill matches the basemap's sea tone (#d9d9d9) so the nation flattens
  // into the background. Border is a distinct slate-violet (not
  // IDLE_STYLE's grey) so it doesn't read as a real council.
  const NATION_STYLE = {
    color: "#6a5f8f",
    weight: 1.5,
    opacity: 0.55,
    fillColor: "#d9d9d9",
    fillOpacity: 1,
    className: "nation-boundary",
  };
  const SELECTED_STYLE = {
    color: "#3ecdd4",
    weight: 3,
    fillOpacity: 0.14,
    // Brighter than the base accent (#50a2a7) so "selected" reads as
    // unmistakably on. Targeted by the pulsing glow in main.html.
    className: "council-boundary--selected",
  };

  // maxBoundsViscosity 1.0 makes the UK bounds solid (no rubber-band drag).
  const ukBounds = L.latLngBounds([49.8, -8.7], [60.9, 1.8]);

  // England's midpoint, not London's -- England is the target scope
  // (~300 councils), London is just the pilot batch.
  const englandMidpoint = [52.5, -1.3];

  const map = L.map(mapEl, {
    maxBounds: ukBounds,
    maxBoundsViscosity: 1.0,
    minZoom: 8,
    zoomControl: false,
  }).setView(englandMidpoint, 8);
  L.control.zoom({ position: "bottomright" }).addTo(map);

  // Esri World Light Gray Canvas, no API key required (CartoDB's anonymous
  // endpoint now needs one). Faded so its detail doesn't compete with a
  // council boundary at high zoom.
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 16,
      opacity: 0.3,
      attribution: "&copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
    }
  ).addTo(map);

  function showNationNote(slug) {
    // Shares a corner with #coverage-badge -- only one visible at a time.
    badgeEl.classList.remove("visible");
    nationNoteEl.textContent = NATION_NOTES[slug] || "";
    nationNoteEl.classList.add("visible");
  }

  function hideNationNote() {
    nationNoteEl.classList.remove("visible");
  }

  // Static overlay, independent of any council selection.
  if (nationsUrl) {
    fetch(nationsUrl)
      .then((response) => {
        if (!response.ok) throw new Error("nations fetch failed: " + response.status);
        return response.json();
      })
      .then((geojson) => {
        L.geoJSON(geojson, {
          style: NATION_STYLE,
          onEachFeature: (feature, featureLayer) => {
            featureLayer.on("click", (event) => {
              L.DomEvent.stopPropagation(event);
              showNationNote(feature.properties.slug);
            });
          },
        }).addTo(map);
      })
      .catch((error) => {
        // eslint-disable-next-line no-console
        console.error("nations fetch failed", error);
      });
  }

  // Click elsewhere on the map dismisses the note.
  map.on("click", hideNationNote);

  function buildIdleLayer(geojson, slug) {
    return L.geoJSON(geojson, {
      style: IDLE_STYLE,
      onEachFeature: (feature, featureLayer) => {
        featureLayer.on("click", (event) => {
          L.DomEvent.stopPropagation(event);
          if (window.councilSwitch) {
            window.councilSwitch.showCouncil(slug);
          } else {
            window.location.href = councilUrlTemplate.replace(
              "__SLUG__",
              encodeURIComponent(slug)
            );
          }
        });
      },
    });
  }

  function buildSelectedLayer(geojson) {
    return L.geoJSON(geojson, { style: SELECTED_STYLE });
  }

  // `promise` is captured at call time, not read live off `coveragePromise`,
  // so a fast council switch can't paint a stale badge over the new one.
  function applyCoverageBadge(promise) {
    promise.then((coverage) => {
      if (promise !== coveragePromise) return;
      if (!coverage || !coverage.has_data_quality_issue) return;
      badgeEl.textContent = coverage.detail_text;
      badgeEl.classList.add("visible");
    });
  }

  // Rejects if uncached and not in the manifest (no boundary file yet) --
  // callers degrade that the same way as a fetch failure.
  function loadAndRenderCouncilBoundary(slug) {
    if (boundaryCache.has(slug)) {
      return Promise.resolve(buildSelectedLayer(boundaryCache.get(slug)));
    }
    const entry = manifestEntriesBySlug && manifestEntriesBySlug[slug];
    if (!entry) {
      return Promise.reject(new Error("no boundary file available for " + slug));
    }
    return fetch(manifestBaseUrl + entry.file)
      .then((response) => {
        if (!response.ok) throw new Error("boundary fetch failed: " + response.status);
        return response.json();
      })
      .then((geojson) => {
        boundaryCache.set(slug, geojson);
        return buildSelectedLayer(geojson);
      });
  }

  // Counterpart to promoting a council: redraws it as idle if cached.
  function demoteSelectedToIdle() {
    if (!selectedLayer || !selectedSlugState) return;
    map.removeLayer(selectedLayer);
    if (boundaryCache.has(selectedSlugState)) {
      const demoted = buildIdleLayer(boundaryCache.get(selectedSlugState), selectedSlugState);
      demoted.addTo(map);
      idleLayersBySlug.set(selectedSlugState, demoted);
    }
    selectedLayer = null;
  }

  // `coverageUrl` may be null -- council-switch.js passes null when the
  // preloaded index says this council has no coverage row, skipping a
  // fetch known to 404.
  function renderSelectedCouncil(slug, coverageUrl) {
    const generation = ++renderGeneration;
    badgeEl.classList.remove("visible");
    hideNationNote();
    demoteSelectedToIdle();

    coveragePromise = coverageUrl
      ? fetch(coverageUrl)
          .then((response) => (response.ok ? response.json() : null))
          .catch(() => null)
      : Promise.resolve(null);
    applyCoverageBadge(coveragePromise);

    if (idleLayersBySlug.has(slug)) {
      map.removeLayer(idleLayersBySlug.get(slug));
      idleLayersBySlug.delete(slug);
    }

    return loadAndRenderCouncilBoundary(slug)
      .then((layer) => {
        if (generation !== renderGeneration) return;

        layer.addTo(map);
        selectedLayer = layer;
        selectedSlugState = slug;

        // Padded past the boundary itself so neighbouring councils stay
        // on-screen and reachable.
        const bounds = layer.getBounds().pad(0.6);
        if (prefersReducedMotion) {
          map.fitBounds(bounds);
        } else {
          map.flyToBounds(bounds, { duration: 0.4, easeLinearity: 0.25, maxZoom: 12 });
        }
      })
      .catch((error) => {
        if (generation !== renderGeneration) return;

        // Not every council has a boundary file yet -- expected, not a
        // bug, so this degrades to a status message.
        selectedSlugState = slug;
        statusEl.textContent = "boundary data not available yet for this council";
        // eslint-disable-next-line no-console
        console.error("boundary fetch failed", error);
      });
  }

  // Counterpart to renderSelectedCouncil for navigating back to "/".
  function showIdleState() {
    ++renderGeneration;
    badgeEl.classList.remove("visible");
    hideNationNote();
    demoteSelectedToIdle();
    selectedSlugState = null;
    coveragePromise = Promise.resolve(null);

    if (prefersReducedMotion) {
      map.setView(englandMidpoint, 8);
    } else {
      map.flyTo(englandMidpoint, 8, { duration: 0.4, easeLinearity: 0.25 });
    }
  }

  // Every council gets a faint idle outline so a selected one still has
  // its neighbours for context. Initial slug skipped -- it gets the bold
  // "selected" treatment below instead.
  if (manifestUrl) {
    fetch(manifestUrl)
      .then((response) => {
        if (!response.ok) throw new Error("manifest fetch failed: " + response.status);
        return response.json();
      })
      .then((manifest) => {
        manifestBaseUrl = manifestUrl.replace(/[^/]+$/, "");
        manifestEntriesBySlug = manifest.councils;
        Object.values(manifest.councils).forEach((entry) => {
          if (entry.slug === initialSelectedSlug) return;

          fetch(manifestBaseUrl + entry.file)
            .then((response) => response.json())
            .then((geojson) => {
              boundaryCache.set(entry.slug, geojson);
              const layer = buildIdleLayer(geojson, entry.slug);
              layer.addTo(map);
              idleLayersBySlug.set(entry.slug, layer);
            })
            .catch((error) => {
              // eslint-disable-next-line no-console
              console.error("idle outline fetch failed", entry.file, error);
            });
        });
      })
      .catch((error) => {
        // eslint-disable-next-line no-console
        console.error("manifest fetch failed", error);
      });
  }

  if (geojsonUrl) {
    // Fetched up front so the first hover shows the badge without a round
    // trip. Unlike a switch, always attempted -- no preloaded index yet
    // to check has_coverage against.
    coveragePromise = mapEl.dataset.coverageUrl
      ? fetch(mapEl.dataset.coverageUrl)
          .then((response) => (response.ok ? response.json() : null))
          .catch(() => null)
      : Promise.resolve(null);
    applyCoverageBadge(coveragePromise);

    fetch(geojsonUrl)
      .then((response) => {
        if (!response.ok) throw new Error("boundary fetch failed: " + response.status);
        return response.json();
      })
      .then((geojson) => {
        boundaryCache.set(initialSelectedSlug, geojson);
        const layer = buildSelectedLayer(geojson);
        layer.addTo(map);
        selectedLayer = layer;
        selectedSlugState = initialSelectedSlug;
        map.fitBounds(layer.getBounds().pad(0.6));
      })
      .catch((error) => {
        statusEl.textContent = "boundary data not available yet for this council";
        // eslint-disable-next-line no-console
        console.error("boundary fetch failed", error);
      });
  }

  window.councilMap = { renderSelectedCouncil, showIdleState };
});

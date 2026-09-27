document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("map");
  const metaEl = document.getElementById("council-meta");
  const badgeEl = document.getElementById("coverage-badge");
  const nationNoteEl = document.getElementById("nation-note");
  const geojsonUrl = mapEl.dataset.geojsonUrl;
  const manifestUrl = mapEl.dataset.manifestUrl;
  const nationsUrl = mapEl.dataset.nationsUrl;
  const initialSelectedSlug = mapEl.dataset.selectedSlug || null;
  const initialSelectedNationSlug = mapEl.dataset.selectedNationSlug || null;

  // slug -> Leaflet layer, populated as the nations GeoJSON loads. Only
  // used to fly the camera to the right nation on load/click -- the note
  // copy itself is server-rendered on /nations/<slug>/ (see
  // apps/councils/nations.py), not duplicated here.
  const nationLayersBySlug = new Map();

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

  // Dark blue-grey fill against the dark basemap so idle councils read as
  // distinct land, not empty void; solid stroke, no dash -- the dash was
  // compensating for a flat light basemap with no fill contrast of its own,
  // which the dark duotone treatment below no longer needs.
  const IDLE_STYLE = { color: "#3a5f6e", weight: 1.5, fillColor: "#16232a", fillOpacity: 0.6 };
  // Mouseover-only -- a lighter version of IDLE_STYLE, since a Leaflet
  // polygon has no native hover affordance of its own (nothing short of an
  // explicit style swap signals "this is clickable").
  const HOVER_STYLE = { color: "#6fa0b3", weight: 2, fillColor: "#1c313a", fillOpacity: 0.8 };
  // Fill matches --color-bg (theme.css) so the nation flattens into the
  // app's own canvas rather than the basemap's sea tone. Border is a
  // distinct slate-violet (not IDLE_STYLE's blue-grey) so it doesn't read
  // as a real council.
  const NATION_STYLE = {
    color: "#6a5f8f",
    weight: 1.5,
    opacity: 0.55,
    fillColor: "#0a0a0d",
    fillOpacity: 1,
    className: "nation-boundary",
  };
  const SELECTED_STYLE = {
    color: "#a5b4fc",
    weight: 3,
    fillOpacity: 0.14,
    // Link tint (--color-link), not the base accent (#6366f1) -- reads as
    // unmistakably "on". Targeted by the hairline glow in main.html.
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

  // Esri World Dark Gray Canvas, same free/no-API-key service family as the
  // light version this replaces (just a different Canvas map ID on the same
  // ArcGIS Online host) -- keeps the map a dark surface consistent with the
  // rest of the app's value hierarchy instead of a bright void next to a
  // dark sidebar. Faded so its own detail doesn't compete with a council
  // boundary at high zoom; #map's own background (theme.css) shows through
  // underneath so the canvas is dark before tiles even load.
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 16,
      opacity: 0.55,
      attribution: "&copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
    }
  ).addTo(map);

  function hideNationNote() {
    nationNoteEl.classList.remove("visible");
  }

  // Same single meta-primary-span shape council-switch.js's setMeta() uses,
  // so this rare fallback message still gets the fixed-single-line/ellipsis
  // treatment instead of a raw text node that could wrap and shift the
  // sidebar underneath it.
  function setMetaFallback(text) {
    metaEl.innerHTML = "";
    const span = document.createElement("span");
    span.className = "meta-primary";
    span.title = text;
    span.textContent = text;
    metaEl.appendChild(span);
  }

  function flyToNation(slug) {
    const layer = nationLayersBySlug.get(slug);
    if (!layer) return;
    const bounds = layer.getBounds().pad(0.2);
    if (prefersReducedMotion) {
      map.fitBounds(bounds);
    } else {
      map.flyToBounds(bounds, { duration: 0.4, easeLinearity: 0.25 });
    }
  }

  // Static overlay, independent of any council selection. A click is a
  // real navigation to that nation's own screen (server-rendered info
  // card, cleared council panel) rather than an in-place popup -- a popup
  // used to leave whatever council panel was already showing stacked
  // underneath it, since this handler had no way to reset state it
  // doesn't own (council-switch.js does).
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
            const slug = feature.properties.slug;
            nationLayersBySlug.set(slug, featureLayer);
            featureLayer.on("click", (event) => {
              L.DomEvent.stopPropagation(event);
              window.location.href = nationUrlTemplate.replace(
                "__SLUG__",
                encodeURIComponent(slug)
              );
            });
          },
        }).addTo(map);

        if (initialSelectedNationSlug) flyToNation(initialSelectedNationSlug);
      })
      .catch((error) => {
        // eslint-disable-next-line no-console
        console.error("nations fetch failed", error);
      });
  }

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
        // A GeoJSON polygon has no native hover affordance -- without this,
        // nothing at all distinguishes a clickable council from inert map
        // decoration until the click itself lands.
        featureLayer.on("mouseover", () => {
          featureLayer.setStyle(HOVER_STYLE);
          featureLayer.bringToFront();
        });
        featureLayer.on("mouseout", () => {
          featureLayer.setStyle(IDLE_STYLE);
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
      badgeEl.querySelector(".badge-body").textContent = coverage.detail_text;
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
    return fetch(manifestBaseUrl + entry.file, { priority: "high" })
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
        setMetaFallback("boundary data not available yet for this council");
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

  // Shared by the bundle path and the legacy per-file fallback.
  function addIdleFeature(feature, slug) {
    if (!slug || slug === initialSelectedSlug || idleLayersBySlug.has(slug)) return;
    const geojson = { type: "FeatureCollection", features: [feature] };
    boundaryCache.set(slug, geojson);
    const layer = buildIdleLayer(geojson, slug);
    layer.addTo(map);
    idleLayersBySlug.set(slug, layer);
  }

  // Builds idle layers in chunks via requestIdleCallback -- at ~300 councils,
  // building every layer synchronously in one tick would stall the main thread.
  function scheduleIdleLayerBuild(features) {
    const CHUNK_SIZE = 25;
    let index = 0;
    function processChunk() {
      const end = Math.min(index + CHUNK_SIZE, features.length);
      for (; index < end; index++) {
        const feature = features[index];
        addIdleFeature(feature, feature.properties && feature.properties.slug);
      }
      if (index < features.length) scheduleNext();
    }
    function scheduleNext() {
      if (typeof requestIdleCallback === "function") {
        requestIdleCallback(processChunk, { timeout: 200 });
      } else {
        setTimeout(processChunk, 0);
      }
    }
    scheduleNext();
  }

  // Fallback for a manifest not yet regenerated with `bundle_file`.
  function loadIdleOutlinesLegacy(manifest) {
    Object.values(manifest.councils).forEach((entry) => {
      if (entry.slug === initialSelectedSlug) return;
      fetch(manifestBaseUrl + entry.file, { priority: "low" })
        .then((response) => response.json())
        .then((geojson) => addIdleFeature(geojson.features[0], entry.slug))
        .catch((error) => {
          // eslint-disable-next-line no-console
          console.error("idle outline fetch failed", entry.file, error);
        });
    });
  }

  // Every council gets a faint idle outline so a selected one still has its
  // neighbours for context. Fetched as one combined FeatureCollection
  // (manifest.bundle_file) instead of one request per council -- 1 request
  // instead of ~300 at England scale. priority: "low" keeps it behind the
  // selected boundary's own fetch.
  if (manifestUrl) {
    fetch(manifestUrl)
      .then((response) => {
        if (!response.ok) throw new Error("manifest fetch failed: " + response.status);
        return response.json();
      })
      .then((manifest) => {
        manifestBaseUrl = manifestUrl.replace(/[^/]+$/, "");
        manifestEntriesBySlug = manifest.councils;

        if (!manifest.bundle_file) {
          loadIdleOutlinesLegacy(manifest);
          return;
        }

        fetch(manifestBaseUrl + manifest.bundle_file, { priority: "low" })
          .then((response) => {
            if (!response.ok) throw new Error("bundle fetch failed: " + response.status);
            return response.json();
          })
          .then((bundle) => scheduleIdleLayerBuild(bundle.features))
          .catch((error) => {
            // eslint-disable-next-line no-console
            console.error("idle bundle fetch failed, falling back to per-file", error);
            loadIdleOutlinesLegacy(manifest);
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

    fetch(geojsonUrl, { priority: "high" })
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
        setMetaFallback("boundary data not available yet for this council");
        // eslint-disable-next-line no-console
        console.error("boundary fetch failed", error);
      });
  }

  window.councilMap = { renderSelectedCouncil, showIdleState };
});

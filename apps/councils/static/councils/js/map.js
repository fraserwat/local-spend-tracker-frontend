document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("map");
  const statusEl = document.getElementById("status");
  const badgeEl = document.getElementById("coverage-badge");
  const geojsonUrl = mapEl.dataset.geojsonUrl;
  const manifestUrl = mapEl.dataset.manifestUrl;
  const initialSelectedSlug = mapEl.dataset.selectedSlug || null;

  // Mutable "current selection" state -- read by the selected layer's own
  // event handlers (via closure, not as a build-time parameter) so a switch
  // just needs to reassign these, not rebuild every handler.
  let selectedSlugState = null;
  let selectedLayer = null;
  let coveragePromise = Promise.resolve(null);

  // slug -> parsed GeoJSON. Populated on first fetch (idle-outline load or a
  // selected-boundary load, whichever happens first for that council) and
  // never evicted, so switching back to a previously-seen council is a
  // zero-network layer rebuild.
  const boundaryCache = new Map();
  // slug -> the idle-styled L.geoJSON layer currently on the map for that
  // council. The selected council's slug is never a key here -- it's
  // removed the moment that council is promoted, and re-added the moment
  // something else is promoted in its place.
  const idleLayersBySlug = new Map();
  // slug -> manifest entry ({file, gss_code, name, ...}), keyed the same way
  // manifest.json itself is -- lets a switch look up any council's boundary
  // file without a second manifest fetch. Populated once the manifest
  // request resolves; a switch to a slug fetched before that happens (or if
  // the manifest fetch fails outright) degrades the same way a genuinely
  // missing boundary file does.
  let manifestEntriesBySlug = null;
  let manifestBaseUrl = "";

  const prefersReducedMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const IDLE_STYLE = { color: "#8b8da3", weight: 2, fillOpacity: 0.04, dashArray: "4 4" };
  const SELECTED_STYLE = {
    color: "#3ecdd4",
    weight: 3,
    fillOpacity: 0.14,
    // Brighter/more saturated than the base accent (#50a2a7) on purpose --
    // a selected map feature needs to read as unmistakably "on" at a
    // glance, not just tinted. This className is what the pulsing glow in
    // main.html's <style> block targets.
    className: "council-boundary--selected",
  };

  // Locks pan/zoom to the UK — maxBoundsViscosity 1.0 makes the bounds
  // fully solid (no rubber-band drag past the edge).
  const ukBounds = L.latLngBounds([49.8, -8.7], [60.9, 1.8]);

  // Roughly the geographic midpoint of England (nr. Fenny Drayton,
  // Leicestershire) -- England is the actual target scope (~300 councils),
  // London is only the pilot batch, so the default view shouldn't be
  // London-centric.
  const englandMidpoint = [52.5, -1.3];

  const map = L.map(mapEl, {
    maxBounds: ukBounds,
    maxBoundsViscosity: 1.0,
    minZoom: 8,
    zoomControl: false,
  }).setView(englandMidpoint, 8);
  L.control.zoom({ position: "bottomright" }).addTo(map);

  // Esri World Light Gray Canvas: minimal no-key basemap built for overlay
  // maps — keeps borough polygons legible instead of competing with full
  // OSM street/POI detail. (CartoDB's anonymous tile endpoint now requires
  // an API key, so that's not an option without signing up for one.)
  // Faded (opacity < 1) so street/building detail doesn't compete with a
  // council boundary once zoomed in close enough for that detail to render.
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 16,
      opacity: 0.3,
      attribution: "&copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
    }
  ).addTo(map);

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
    return L.geoJSON(geojson, {
      style: SELECTED_STYLE,
      onEachFeature: (feature, featureLayer) => {
        featureLayer.on("mouseover", () => {
          // Reads `coveragePromise` live (not a captured parameter) so a
          // switch reassigning it doesn't need this handler rebuilt.
          coveragePromise.then((coverage) => {
            if (!coverage || !coverage.has_data_quality_issue) return;
            badgeEl.textContent = coverage.detail_text;
            badgeEl.classList.add("visible");
          });
        });
        featureLayer.on("mouseout", () => {
          badgeEl.classList.remove("visible");
        });
      },
    });
  }

  // Fetch-or-reuse-cached GeoJSON for `slug`, then build it as a selected-
  // style layer. Rejects if the boundary was never fetched AND isn't in the
  // manifest (no boundary file exists yet for that council) -- callers
  // degrade that the same way a fetch failure degrades.
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

  // Removes the current selection from the map and, if its geometry is
  // cached, redraws it as an idle outline in its place -- the counterpart
  // to promoting a council to selected. A no-op when nothing is selected.
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

  // Switches the map to `slug` without a page reload: demotes the current
  // selection back to an idle outline, promotes the target (reusing its
  // idle layer/cached geometry if either already exists), and flies the
  // camera to the new bounds. `coverageUrl` may be null (council-switch.js
  // passes null when the preloaded index says this council has no coverage
  // row, skipping a fetch known to 404).
  function renderSelectedCouncil(slug, coverageUrl) {
    badgeEl.classList.remove("visible");
    demoteSelectedToIdle();

    coveragePromise = coverageUrl
      ? fetch(coverageUrl)
          .then((response) => (response.ok ? response.json() : null))
          .catch(() => null)
      : Promise.resolve(null);

    if (idleLayersBySlug.has(slug)) {
      map.removeLayer(idleLayersBySlug.get(slug));
      idleLayersBySlug.delete(slug);
    }

    return loadAndRenderCouncilBoundary(slug)
      .then((layer) => {
        layer.addTo(map);
        selectedLayer = layer;
        selectedSlugState = slug;

        // Padded well past the selected boundary itself -- fitting tightly
        // to just this council leaves neighbouring councils off-screen,
        // making their idle outlines effectively unreachable without the
        // user manually zooming out first.
        const bounds = layer.getBounds().pad(0.6);
        if (prefersReducedMotion) {
          map.fitBounds(bounds);
        } else {
          map.flyToBounds(bounds, { duration: 0.4, easeLinearity: 0.25, maxZoom: 12 });
        }
      })
      .catch((error) => {
        // Only a handful of councils have a fetched boundary so far (Phase
        // 7 scales this to the rest) -- a missing file for any other
        // council is expected, not a bug, so this degrades to a status
        // message rather than an unhandled rejection.
        selectedSlugState = slug;
        statusEl.textContent = "boundary data not available yet for this council";
        // eslint-disable-next-line no-console
        console.error("boundary fetch failed", error);
      });
  }

  // Counterpart to renderSelectedCouncil for navigating back to "/" -- no
  // council selected, camera returns to the England-wide default view.
  function showIdleState() {
    badgeEl.classList.remove("visible");
    demoteSelectedToIdle();
    selectedSlugState = null;
    coveragePromise = Promise.resolve(null);

    if (prefersReducedMotion) {
      map.setView(englandMidpoint, 8);
    } else {
      map.flyTo(englandMidpoint, 8, { duration: 0.4, easeLinearity: 0.25 });
    }
  }

  // Every council with a fetched boundary gets drawn as a faint idle
  // outline, on the landing page AND on a specific council's page -- a
  // selected council needs its neighbours visible for geographic context,
  // not to float alone on a blank basemap. The initially-selected slug (if
  // any) is skipped here since it gets the bold "selected" treatment below
  // instead.
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
    // Fetched once up front (not per hover) so the first hover shows the
    // badge immediately instead of waiting on a network round-trip. A
    // missing/failed coverage row (no data loaded yet for this council)
    // just means the badge never has anything to show -- not an error
    // state. Initial load always attempts this fetch (unlike a switch,
    // which can skip it via the preloaded index's has_coverage flag) since
    // there's no index loaded yet at this point in the page lifecycle.
    coveragePromise = mapEl.dataset.coverageUrl
      ? fetch(mapEl.dataset.coverageUrl)
          .then((response) => (response.ok ? response.json() : null))
          .catch(() => null)
      : Promise.resolve(null);

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

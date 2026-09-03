document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("map");
  const statusEl = document.getElementById("status");
  const badgeEl = document.getElementById("coverage-badge");
  const geojsonUrl = mapEl.dataset.geojsonUrl;
  const manifestUrl = mapEl.dataset.manifestUrl;
  const spendUrl = mapEl.dataset.spendUrl;
  const coverageUrl = mapEl.dataset.coverageUrl;
  const selectedSlug = mapEl.dataset.selectedSlug;

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

  // Every council with a fetched boundary gets drawn as a faint idle
  // outline, on the landing page AND on a specific council's page -- a
  // selected council needs its neighbours visible for geographic context,
  // not to float alone on a blank basemap. The selected slug (if any) is
  // skipped here since it gets the bold "selected" treatment below instead.
  // Idle outlines are clickable straight through to that council's page
  // (same "council-detail" route the sidebar links use, via the
  // councilUrlTemplate global set in _council_sidebar.html).
  if (manifestUrl) {
    fetch(manifestUrl)
      .then((response) => {
        if (!response.ok) throw new Error("manifest fetch failed: " + response.status);
        return response.json();
      })
      .then((manifest) => {
        const baseUrl = manifestUrl.replace(/[^/]+$/, "");
        Object.values(manifest.councils).forEach((entry) => {
          if (entry.slug === selectedSlug) return;

          fetch(baseUrl + entry.file)
            .then((response) => response.json())
            .then((geojson) => {
              L.geoJSON(geojson, {
                style: { color: "#8b8da3", weight: 2, fillOpacity: 0.04, dashArray: "4 4" },
                onEachFeature: (feature, featureLayer) => {
                  featureLayer.on("click", (event) => {
                    L.DomEvent.stopPropagation(event);
                    window.location.href = councilUrlTemplate.replace(
                      "__SLUG__",
                      encodeURIComponent(entry.slug)
                    );
                  });
                },
              }).addTo(map);
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

  if (!geojsonUrl) return;

  // Fetched once up front (not per hover) so the first hover shows the
  // badge immediately instead of waiting on a network round-trip. A
  // missing/failed coverage row (no data loaded yet for this council) just
  // means the badge never has anything to show -- not an error state.
  const coveragePromise = coverageUrl
    ? fetch(coverageUrl)
        .then((response) => (response.ok ? response.json() : null))
        .catch(() => null)
    : Promise.resolve(null);

  fetch(geojsonUrl)
    .then((response) => {
      if (!response.ok) throw new Error("boundary fetch failed: " + response.status);
      return response.json();
    })
    .then((geojson) => {
      const layer = L.geoJSON(geojson, {
        // Brighter/more saturated than the base accent (#50a2a7) on
        // purpose -- a selected map feature needs to read as unmistakably
        // "on" at a glance, not just tinted. The className hook is what
        // the pulsing glow in main.html's <style> block targets.
        style: {
          color: "#3ecdd4",
          weight: 3,
          fillOpacity: 0.14,
          className: "council-boundary--selected",
        },
        onEachFeature: (feature, featureLayer) => {
          featureLayer.on("click", (event) => {
            // Stops the click reaching map's own handler below, so
            // inside/outside clicks are mutually exclusive.
            L.DomEvent.stopPropagation(event);
            // Same destination as the "view spend" link shown before any
            // click -- clicking the boundary is just a faster path there,
            // not a different action.
            if (spendUrl) {
              statusEl.innerHTML = "";
              const link = document.createElement("a");
              link.href = spendUrl;
              link.className = "spend-cta";
              link.textContent = `View ${feature.properties.name} Spend`;
              statusEl.appendChild(link);
            } else {
              statusEl.textContent = `clicked inside: ${feature.properties.name}`;
            }
          });
          featureLayer.on("mouseover", () => {
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
      }).addTo(map);

      map.fitBounds(layer.getBounds());
    })
    .catch((error) => {
      // Only a handful of councils have a fetched boundary so far (Phase 7
      // scales this to the rest) -- a missing file for any other council is
      // expected, not a bug, so this degrades to a status message rather
      // than an unhandled rejection.
      statusEl.textContent = "boundary data not available yet for this council";
      // eslint-disable-next-line no-console
      console.error("boundary fetch failed", error);
    });

  map.on("click", () => {
    statusEl.textContent = "clicked outside";
  });
});

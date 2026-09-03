document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("map");
  const statusEl = document.getElementById("status");
  const geojsonUrl = mapEl.dataset.geojsonUrl;
  const manifestUrl = mapEl.dataset.manifestUrl;

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

  // No council selected yet (the "/" landing state) -- draw every council
  // with a fetched boundary as a faint, non-interactive outline so there's
  // a visible affordance for "these are the clickable areas", clearly
  // lighter than the selected-council style below. No inside/outside click
  // tracking applies yet since no single council is in focus.
  if (!geojsonUrl) {
    if (!manifestUrl) return;

    fetch(manifestUrl)
      .then((response) => {
        if (!response.ok) throw new Error("manifest fetch failed: " + response.status);
        return response.json();
      })
      .then((manifest) => {
        const baseUrl = manifestUrl.replace(/[^/]+$/, "");
        Object.values(manifest.councils).forEach((entry) => {
          fetch(baseUrl + entry.file)
            .then((response) => response.json())
            .then((geojson) => {
              L.geoJSON(geojson, {
                interactive: false,
                style: { color: "#8a94a6", weight: 2, fillOpacity: 0.04, dashArray: "4 4" },
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

    return;
  }

  fetch(geojsonUrl)
    .then((response) => {
      if (!response.ok) throw new Error("boundary fetch failed: " + response.status);
      return response.json();
    })
    .then((geojson) => {
      const layer = L.geoJSON(geojson, {
        style: { color: "#0f3d5c", weight: 3, fillOpacity: 0.22 },
        onEachFeature: (feature, featureLayer) => {
          featureLayer.on("click", (event) => {
            // Stops the click reaching map's own handler below, so
            // inside/outside clicks are mutually exclusive.
            L.DomEvent.stopPropagation(event);
            statusEl.textContent = `clicked inside: ${feature.properties.name}`;
          });
        },
      }).addTo(map);

      map.fitBounds(layer.getBounds());
    })
    .catch((error) => {
      // Only Haringey has a fetched boundary today (Phase 7 scales this to
      // the rest) -- a missing file for any other council is expected, not
      // a bug, so this degrades to a status message rather than an
      // unhandled rejection.
      statusEl.textContent = "boundary data not available yet for this council";
      // eslint-disable-next-line no-console
      console.error("boundary fetch failed", error);
    });

  map.on("click", () => {
    statusEl.textContent = "clicked outside";
  });
});

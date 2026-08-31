document.addEventListener("DOMContentLoaded", () => {
  const mapEl = document.getElementById("map");
  const statusEl = document.getElementById("status");
  const geojsonUrl = mapEl.dataset.geojsonUrl;

  // Locks pan/zoom to the UK — maxBoundsViscosity 1.0 makes the bounds
  // fully solid (no rubber-band drag past the edge).
  const ukBounds = L.latLngBounds([49.8, -8.7], [60.9, 1.8]);

  const map = L.map(mapEl, {
    maxBounds: ukBounds,
    maxBoundsViscosity: 1.0,
    minZoom: 8,
  }).setView([54.5, -3], 8);

  // Esri World Light Gray Canvas: minimal no-key basemap built for overlay
  // maps — keeps borough polygons legible instead of competing with full
  // OSM street/POI detail. (CartoDB's anonymous tile endpoint now requires
  // an API key, so that's not an option without signing up for one.)
  L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 16,
      attribution: "&copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
    }
  ).addTo(map);

  // No council selected yet (the "/" landing state) -- leave a bare,
  // pannable UK map with no boundary to fetch and no inside/outside status
  // to track.
  if (!geojsonUrl) return;

  fetch(geojsonUrl)
    .then((response) => {
      if (!response.ok) throw new Error("boundary fetch failed: " + response.status);
      return response.json();
    })
    .then((geojson) => {
      const layer = L.geoJSON(geojson, {
        style: { color: "#1a5276", weight: 2, fillOpacity: 0.15 },
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

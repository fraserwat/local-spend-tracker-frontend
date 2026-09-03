(function () {
  "use strict";

  var container = document.getElementById("council-search-container");
  var status = document.getElementById("search-status");
  var regionBrowse = document.getElementById("council-region-browse");
  if (!container) return;

  // The region groups and the search suggestions both live in the same
  // sidebar slot -- showing both at once is what made the list look like
  // it was pushing itself down the page. Swap one for the other based on
  // whether there's a live query, rather than stacking them.
  function toggleRegionBrowse(query) {
    if (!regionBrowse) return;
    regionBrowse.hidden = query.length > 0;
  }

  var indexUrl = container.getAttribute("data-index-url");

  function setStatus(message) {
    if (status) status.textContent = message;
  }

  function councilUrl(slug) {
    return councilUrlTemplate.replace("__SLUG__", encodeURIComponent(slug));
  }

  if (typeof accessibleAutocomplete === "undefined") {
    // CDN blocked or failed to load -- the region-group <details> below
    // still work with zero JS, so search is the only thing degrading here.
    setStatus("Search is unavailable right now. Browse by region below instead.");
    return;
  }

  fetch(indexUrl)
    .then(function (response) {
      if (!response.ok) throw new Error("index fetch failed: " + response.status);
      return response.json();
    })
    .then(function (councils) {
      // accessible-autocomplete's built-in array-source filter calls
      // .toLowerCase() directly on each item, so it only works for plain
      // strings. A custom `source` function instead lets suggestions carry
      // the full council object (including slug) through to onConfirm --
      // a name-keyed lookup would silently collide if two councils ever
      // share a display name (not true of today's 32, but a real risk once
      // this scales towards England's ~300 councils, where duplicate
      // district names across different counties are common).
      function filterCouncils(query, populateResults) {
        var needle = query.toLowerCase();
        populateResults(
          councils.filter(function (council) {
            return council.name.toLowerCase().indexOf(needle) !== -1;
          })
        );
      }

      accessibleAutocomplete({
        element: container,
        id: "council-search",
        placeholder: "Start typing a council name",
        source: filterCouncils,
        // Suggestions only replace "Browse by region" once there's
        // something to filter by -- an empty query would otherwise match
        // every council (see filterCouncils' indexOf) and swap the region
        // list out on focus alone, before the user's typed anything.
        minLength: 1,
        templates: {
          inputValue: function (council) {
            return council ? council.name : "";
          },
          suggestion: function (council) {
            return council && council.name ? council.name : council;
          },
        },
        onConfirm: function (confirmed) {
          if (confirmed && confirmed.slug) {
            window.location.href = councilUrl(confirmed.slug);
          }
        },
      });

      // accessible-autocomplete re-creates its <input> on init, so the
      // listener has to be delegated from the (stable) container rather
      // than attached directly to the input element.
      container.addEventListener("input", function (event) {
        if (event.target && event.target.id === "council-search") {
          toggleRegionBrowse(event.target.value.trim());
        }
      });
    })
    .catch(function (error) {
      setStatus("Search is unavailable right now. Browse by region below instead.");
      // eslint-disable-next-line no-console
      console.error("council-index fetch failed", error);
    });
})();

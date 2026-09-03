(function () {
  "use strict";

  var container = document.getElementById("council-search-container");
  var input = document.getElementById("council-search");
  var status = document.getElementById("search-status");
  var resultsList = document.getElementById("council-search-results");
  var regionBrowse = document.getElementById("council-region-browse");
  if (!container || !input || !resultsList || !regionBrowse) return;

  var indexUrl = container.getAttribute("data-index-url");

  function setStatus(message) {
    if (status) status.textContent = message;
  }

  function councilUrl(slug) {
    return councilUrlTemplate.replace("__SLUG__", encodeURIComponent(slug));
  }

  CouncilIndex.load(indexUrl)
    .then(function (councils) {
      // council-index.json is generated pre-sorted by name (see
      // generate_council_index), so filtering preserves alphabetical order
      // without the results needing a sort step here.
      function render(query) {
        var needle = query.toLowerCase();
        var matches = councils.filter(function (council) {
          return council.name.toLowerCase().indexOf(needle) !== -1;
        });

        // The region groups and the search results both live in the same
        // sidebar slot -- showing both at once (or opening a dropdown on
        // top of them) is what made the list look like it was pushing
        // itself down the page. Swap one for the other instead of stacking
        // them.
        if (!query) {
          resultsList.hidden = true;
          resultsList.textContent = "";
          regionBrowse.hidden = false;
          setStatus("");
          return;
        }

        regionBrowse.hidden = true;
        resultsList.hidden = false;
        resultsList.textContent = "";
        matches.forEach(function (council) {
          var li = document.createElement("li");
          var a = document.createElement("a");
          a.href = councilUrl(council.slug);
          // data-slug lets council-switch.js's delegated .council-sidebar
          // click listener intercept these the same way it does the
          // region-browse links -- no separate wiring needed here.
          a.dataset.slug = council.slug;
          a.textContent = council.name;
          li.appendChild(a);
          resultsList.appendChild(li);
        });
        setStatus(
          matches.length === 1 ? "1 council found" : matches.length + " councils found"
        );
      }

      input.addEventListener("input", function () {
        render(input.value.trim());
      });
    })
    .catch(function (error) {
      setStatus("Search is unavailable right now. Browse by region below instead.");
      input.disabled = true;
      // eslint-disable-next-line no-console
      console.error("council-index fetch failed", error);
    });
})();

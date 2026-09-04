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
      // Pre-sorted by name (see generate_council_index), so filtering
      // preserves order without a sort step here.
      function render(query) {
        var needle = query.toLowerCase();
        var matches = councils.filter(function (council) {
          return council.name.toLowerCase().indexOf(needle) !== -1;
        });

        // Region groups and search results share one sidebar slot -- swap
        // rather than stack, or the list pushes itself down the page.
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
          // Lets council-switch.js's delegated click listener intercept
          // this the same way as region-browse links.
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

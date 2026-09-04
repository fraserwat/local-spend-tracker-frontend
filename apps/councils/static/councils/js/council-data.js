// Shared council-index.json loader for picker.js and council-switch.js --
// whichever loads first triggers the fetch, the other reuses the promise.
window.CouncilIndex = (function () {
  "use strict";

  var promise = null;

  function load(url) {
    if (!promise) {
      promise = fetch(url)
        .then(function (response) {
          if (!response.ok) throw new Error("council-index fetch failed: " + response.status);
          return response.json();
        })
        .catch(function (error) {
          // Clear the cache so the next load() retries instead of
          // replaying this rejection.
          promise = null;
          throw error;
        });
    }
    return promise;
  }

  function findBySlug(rows, slug) {
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].slug === slug) return rows[i];
    }
    return null;
  }

  return { load: load, findBySlug: findBySlug };
})();

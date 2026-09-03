// Shared council-index.json loader -- picker.js (search) and
// council-switch.js (in-page switching) both need the same council list.
// Whichever loads first triggers the single fetch; the other reuses the
// same promise instead of firing a second request.
window.CouncilIndex = (function () {
  "use strict";

  var promise = null;

  function load(url) {
    if (!promise) {
      promise = fetch(url).then(function (response) {
        if (!response.ok) throw new Error("council-index fetch failed: " + response.status);
        return response.json();
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

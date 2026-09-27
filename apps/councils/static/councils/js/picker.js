(function () {
  "use strict";

  var input = document.getElementById("council-search");
  var status = document.getElementById("search-status");
  var list = document.getElementById("council-list");
  if (!input || !status || !list) return;

  // Server-rendered rows already carry the full council set (see
  // _council_sidebar.html) -- filtering hides/shows them in place instead
  // of re-fetching or rebuilding from council-index.json, so there's no
  // second data source and no network request on every keystroke.
  var rows = Array.prototype.slice.call(list.querySelectorAll("li[data-name]"));

  // A dedicated "no matches" row, distinct from the server-rendered
  // `{% empty %}` row (that one means "zero councils exist at all" and
  // must never be touched by search).
  var emptyRow = document.createElement("li");
  emptyRow.className = "no-results";
  emptyRow.hidden = true;
  list.appendChild(emptyRow);

  function setStatus(message) {
    status.textContent = message;
  }

  function render(query) {
    var needle = query.toLowerCase();
    var visibleCount = 0;

    rows.forEach(function (row) {
      var matches = !needle || row.dataset.name.indexOf(needle) !== -1;
      row.hidden = !matches;
      if (matches) visibleCount++;
    });

    if (!query) {
      emptyRow.hidden = true;
      setStatus("");
      return;
    }

    emptyRow.hidden = visibleCount !== 0;
    emptyRow.textContent = visibleCount === 0 ? "No councils match “" + query + "”." : "";
    setStatus(
      visibleCount === 0
        ? "No councils found"
        : visibleCount === 1
          ? "1 council found"
          : visibleCount + " councils found"
    );
  }

  input.addEventListener("input", function () {
    render(input.value.trim());
  });
})();

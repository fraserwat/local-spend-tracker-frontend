// Orchestrates in-page council switching: history/URL, page <title>, the
// #status prompt, sidebar aria-current, focus, and a screen-reader
// announcement. map.js owns the camera/boundary side of a switch
// (window.councilMap); this file owns everything else and calls into that.
//
// Progressive enhancement: every entry point here is reached either by
// intercepting a real <a href> click (preventDefault, then this takes over)
// or by another script (map.js's idle-outline click, picker.js's search
// confirm) already carrying the same window.councilSwitch-with-fallback
// pattern. If this script fails to load, those real hrefs/hard navigations
// are exactly what fires instead -- no separate no-JS code path needed.
document.addEventListener("DOMContentLoaded", () => {
  const sidebarEl = document.querySelector(".council-sidebar");
  const statusEl = document.getElementById("status");
  const headingEl = document.getElementById("council-route-heading");
  const announcerEl = document.getElementById("council-switch-announcer");
  const indexUrl = document
    .getElementById("council-search-container")
    .getAttribute("data-index-url");

  // Turns the "{slug}" placeholder route template into a matcher for
  // popstate, so parsing stays coupled to the real route pattern instead of
  // a second hardcoded regex.
  const councilRouteRegex = new RegExp(
    "^" + councilUrlTemplate.replace("__SLUG__", "([^/]+)") + "$"
  );

  function announce(message) {
    // Clearing first, then setting on a later tick, forces the change to
    // register as a fresh update even if two switches in a row would
    // otherwise produce the same text -- an unchanged aria-live region
    // doesn't get re-announced. setTimeout rather than requestAnimationFrame
    // since this only needs to outlast a synchronous DOM write, not sync
    // with a paint -- rAF can stall indefinitely in a backgrounded/
    // non-rendering tab.
    announcerEl.textContent = "";
    setTimeout(() => {
      announcerEl.textContent = message;
    }, 0);
  }

  function setAriaCurrent(slug) {
    const previous = sidebarEl.querySelector("a[aria-current='page']");
    if (previous) previous.removeAttribute("aria-current");
    if (slug) {
      const next = sidebarEl.querySelector('a[data-slug="' + slug + '"]');
      if (next) next.setAttribute("aria-current", "page");
    }
  }

  function showCouncil(slug, opts) {
    opts = opts || {};
    const targetUrl = councilUrlTemplate.replace("__SLUG__", encodeURIComponent(slug));

    if (!window.councilMap) {
      window.location.href = targetUrl;
      return;
    }

    CouncilIndex.load(indexUrl).then((rows) => {
      const row = CouncilIndex.findBySlug(rows, slug);
      if (!row) {
        // Not in the preloaded index (stale cache, or a slug that doesn't
        // exist) -- a real navigation lets the server 404 it properly
        // rather than this script guessing at a degraded in-page state.
        window.location.href = targetUrl;
        return;
      }

      const coverageUrl =
        row.has_coverage === true
          ? councilCoverageUrlTemplate.replace("__SLUG__", encodeURIComponent(slug))
          : null;
      window.councilMap.renderSelectedCouncil(slug, coverageUrl);

      document.title = row.name + " — Local Spend Tracker";
      statusEl.innerHTML = "";
      const link = document.createElement("a");
      link.href = councilSpendUrlTemplate.replace("__SLUG__", encodeURIComponent(slug));
      link.className = "spend-cta";
      link.textContent = "View " + row.name + " Spend";
      statusEl.appendChild(link);
      setAriaCurrent(slug);
      headingEl.textContent = row.name;
      headingEl.focus();
      announce("Now showing " + row.name);

      if (!opts.fromPopState) {
        history.pushState({ slug: slug }, "", targetUrl);
      }
    });
  }

  function showPicker(opts) {
    opts = opts || {};
    if (window.councilMap) window.councilMap.showIdleState();

    document.title = "Local Spend Tracker";
    statusEl.textContent = "select a council to see its boundary";
    setAriaCurrent(null);
    headingEl.textContent = "Select a council";
    headingEl.focus();
    announce("Showing council picker");

    if (!opts.fromPopState) {
      history.pushState({}, "", "/");
    }
  }

  sidebarEl.addEventListener("click", (event) => {
    // Preserve middle-click / cmd-click / ctrl-click "open in new tab" on
    // the real sidebar links -- only a plain left click gets intercepted.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    const link = event.target.closest("a[data-slug]");
    if (!link) return;
    event.preventDefault();
    showCouncil(link.dataset.slug);
  });

  window.addEventListener("popstate", () => {
    const match = councilRouteRegex.exec(location.pathname);
    if (match) {
      showCouncil(decodeURIComponent(match[1]), { fromPopState: true });
    } else {
      showPicker({ fromPopState: true });
    }
  });

  window.councilSwitch = { showCouncil: showCouncil, showPicker: showPicker };
});

// Orchestrates in-page council switching: history/URL, <title>, #status,
// sidebar aria-current, focus, screen-reader announcement. map.js owns the
// camera/boundary side (window.councilMap); this owns everything else.
//
// Progressive enhancement: every entry point intercepts a real <a href> or
// another script's window.councilSwitch-with-fallback call. If this script
// fails to load, those real hrefs/hard navigations fire instead.
document.addEventListener("DOMContentLoaded", () => {
  const sidebarEl = document.querySelector(".council-sidebar");
  const statusEl = document.getElementById("status");
  const headingEl = document.getElementById("council-route-heading");
  const announcerEl = document.getElementById("council-switch-announcer");
  const indexUrl = document
    .getElementById("council-search-container")
    .getAttribute("data-index-url");

  // Derives the popstate matcher from the real route template, instead of
  // a second hardcoded regex.
  const councilRouteRegex = new RegExp(
    "^" + councilUrlTemplate.replace("__SLUG__", "([^/]+)") + "$"
  );

  // Bumped on every showCouncil()/showPicker() call; a stale async
  // CouncilIndex.load().then() compares against this before touching
  // document.title/statusEl/headingEl.
  let switchGeneration = 0;

  function announce(message) {
    // Clear-then-set-on-a-later-tick forces a re-announce even for
    // identical text (an unchanged aria-live region stays silent).
    // setTimeout, not rAF, since rAF can stall in a backgrounded tab.
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
    const generation = ++switchGeneration;
    const targetUrl = councilUrlTemplate.replace("__SLUG__", encodeURIComponent(slug));

    if (!window.councilMap) {
      window.location.href = targetUrl;
      return;
    }

    CouncilIndex.load(indexUrl)
      .then((rows) => {
        if (generation !== switchGeneration) return;

        const row = CouncilIndex.findBySlug(rows, slug);
        if (!row) {
          // Not in the index -- real navigation lets the server 404 it.
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
      })
      .catch(() => {
        // Index load failed -- fall back to a real navigation.
        if (generation !== switchGeneration) return;
        window.location.href = targetUrl;
      });
  }

  function showPicker(opts) {
    opts = opts || {};
    switchGeneration++;
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
    // Only a plain left click is intercepted -- preserves open-in-new-tab.
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

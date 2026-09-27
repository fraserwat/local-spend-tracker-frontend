// Orchestrates in-page council switching: history/URL, <title>, the
// heading/meta/CTA trio, sidebar aria-current, focus, screen-reader
// announcement. map.js owns the camera/boundary side (window.councilMap);
// this owns everything else.
//
// Progressive enhancement: every entry point intercepts a real <a href> or
// another script's window.councilSwitch-with-fallback call. If this script
// fails to load, those real hrefs/hard navigations fire instead.
document.addEventListener("DOMContentLoaded", () => {
  const sidebarEl = document.querySelector(".council-sidebar");
  const headingEl = document.getElementById("council-route-heading");
  const metaEl = document.getElementById("council-meta");
  const ctaEl = document.getElementById("council-cta");
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
  // document.title/headingEl/metaEl/ctaEl.
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

  // Mirrors django.utils.timesince's default depth=2 output (the server
  // renders the same "Updated ..." clause with the real timesince() on a
  // hard load, e.g. "2 weeks, 3 days ago", not just "2 weeks ago") -- an
  // in-page switch showing a shorter, differently-shaped string than a
  // hard navigation to the same URL would be its own small inconsistency.
  // council-index.json only ever carries the raw timestamp, never a
  // pre-rendered string, so this always reflects "now" rather than
  // whenever the index file was last regenerated.
  const TIMESINCE_CHUNKS = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  function relativeTime(isoString) {
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(isoString).getTime()) / 1000));
    for (let i = 0; i < TIMESINCE_CHUNKS.length; i++) {
      const [name, secondsPerUnit] = TIMESINCE_CHUNKS[i];
      const count = Math.floor(seconds / secondsPerUnit);
      if (count < 1) continue;

      let result = count + " " + name + (count === 1 ? "" : "s");
      const next = TIMESINCE_CHUNKS[i + 1];
      if (next) {
        const count2 = Math.floor((seconds - count * secondsPerUnit) / next[1]);
        if (count2 >= 1) result += ", " + count2 + " " + next[0] + (count2 === 1 ? "" : "s");
      }
      return result + " ago";
    }
    return "just now";
  }

  // Same two-span shape council_meta's server-rendered branch uses, so an
  // in-page switch matches a hard navigation to the same URL exactly.
  function setMeta(primaryText, secondaryText) {
    metaEl.innerHTML = "";
    const primary = document.createElement("span");
    primary.className = "meta-primary";
    primary.title = primaryText;
    primary.textContent = primaryText;
    metaEl.appendChild(primary);
    if (secondaryText) {
      const sep = document.createElement("span");
      sep.className = "meta-sep";
      sep.textContent = "·";
      metaEl.appendChild(sep);
      const secondary = document.createElement("span");
      secondary.className = "meta-secondary";
      secondary.textContent = secondaryText;
      metaEl.appendChild(secondary);
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
        headingEl.textContent = row.name;
        headingEl.title = row.name;
        headingEl.classList.add("council-heading--serif");
        setMeta(row.region_display, row.last_loaded_at ? "Updated " + relativeTime(row.last_loaded_at) : null);
        // Same <a> element as the ghost state (see showPicker) -- only its
        // href/class/disabledness change, never its node type.
        ctaEl.href = councilSpendUrlTemplate.replace("__SLUG__", encodeURIComponent(slug));
        ctaEl.classList.remove("council-cta--ghost");
        ctaEl.removeAttribute("aria-disabled");
        ctaEl.removeAttribute("tabindex");
        setAriaCurrent(slug);
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
    headingEl.textContent = "Select a council";
    headingEl.removeAttribute("title");
    headingEl.classList.remove("council-heading--serif");
    setMeta("Select a council to see its spend", null);
    ctaEl.removeAttribute("href");
    ctaEl.classList.add("council-cta--ghost");
    ctaEl.setAttribute("aria-disabled", "true");
    ctaEl.setAttribute("tabindex", "-1");
    setAriaCurrent(null);
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

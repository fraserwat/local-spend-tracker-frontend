// Progressive enhancement over the plain preset links + day/month/year
// fields in the Date range cluster -- see #date-fallback in
// transactions.html. Same contract as autocomplete.js: the form posts
// date_from_0/1/2 and date_to_0/1/2 and filters correctly with this
// script entirely absent, so a fetch failure or JS error here just leaves
// the user with the plain GOV.UK-style fields, never a broken filter.
//
// Merges three reference patterns onto that one no-JS baseline:
//   - Stripe Dashboard's preset dropdown, separate from the custom-range
//     control, presets apply immediately, Custom stays open for editing.
//   - Airbnb's dual-month calendar: click a start day, click an end day,
//     the days between shade as one connected band.
//   - Vercel Web Analytics' pattern (drag across a chart) doesn't apply
//     here -- this app has no chart to drag across, so it's left out.
//
// Pure date math is exposed on window.DateRangePicker so it can be unit
// tested (see tests/date-range-picker.test.js) without a DOM.
(function () {
  const MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const WEEKDAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

  function daysInMonth(year, monthIndex) {
    return new Date(year, monthIndex + 1, 0).getDate();
  }

  // Monday-first weekday index (0=Mon..6=Sun) -- matches the WEEKDAY_LABELS
  // header and the rest of this app's UK-audience conventions.
  function weekdayIndex(date) {
    return (date.getDay() + 6) % 7;
  }

  function buildMonthWeeks(year, monthIndex) {
    const total = daysInMonth(year, monthIndex);
    const weeks = [];
    let week = new Array(weekdayIndex(new Date(year, monthIndex, 1))).fill(null);
    for (let day = 1; day <= total; day++) {
      week.push(new Date(year, monthIndex, day));
      if (week.length === 7) {
        weeks.push(week);
        week = [];
      }
    }
    if (week.length) {
      while (week.length < 7) week.push(null);
      weeks.push(week);
    }
    return weeks;
  }

  function sameDay(a, b) {
    return !!a && !!b && a.getFullYear() === b.getFullYear()
      && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function isBefore(a, b) {
    return a.getTime() < b.getTime();
  }

  function inRange(date, start, end) {
    if (!start || !end) return false;
    return isBefore(start, date) && isBefore(date, end);
  }

  // Pure reducer for a calendar day click -- no start yet, or a range
  // already closed (start+end both set): begin a new single-day selection.
  // One end open: close it, swapping if the new click lands before start.
  function commitClick(state, clicked) {
    if (!state.start || (state.start && state.end)) {
      return { start: clicked, end: null };
    }
    if (isBefore(clicked, state.start)) {
      return { start: clicked, end: state.start };
    }
    return { start: state.start, end: clicked };
  }

  function parseISODate(iso) {
    if (!iso) return null;
    const parts = iso.split("-").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function parseDMYInputs(dayEl, monthEl, yearEl) {
    const day = parseInt(dayEl.value, 10);
    const month = parseInt(monthEl.value, 10);
    const year = parseInt(yearEl.value, 10);
    if (!day || !month || !year) return null;
    return new Date(year, month - 1, day);
  }

  function writeDMYInputs(dayEl, monthEl, yearEl, date) {
    if (!date) {
      dayEl.value = "";
      monthEl.value = "";
      yearEl.value = "";
      return;
    }
    dayEl.value = String(date.getDate());
    monthEl.value = String(date.getMonth() + 1);
    yearEl.value = String(date.getFullYear());
  }

  window.DateRangePicker = {
    daysInMonth,
    weekdayIndex,
    buildMonthWeeks,
    sameDay,
    isBefore,
    inRange,
    commitClick,
    parseISODate,
    parseDMYInputs,
    writeDMYInputs,
    MONTH_NAMES,
    WEEKDAY_LABELS,
  };

  document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("date-range-field");
    if (!container) return;
    const trigger = document.getElementById("date-trigger");
    const triggerLabel = document.getElementById("date-trigger-label");
    const fallback = document.getElementById("date-fallback");
    const form = container.closest("form");
    const fromDay = document.getElementById("id_date_from_0");
    const fromMonth = document.getElementById("id_date_from_1");
    const fromYear = document.getElementById("id_date_from_2");
    const toDay = document.getElementById("id_date_to_0");
    const toMonth = document.getElementById("id_date_to_1");
    const toYear = document.getElementById("id_date_to_2");
    // Bail out (leaving the no-JS fallback visible and untouched) rather
    // than half-enhance -- every one of these has to exist for the panel
    // to have anywhere to write its selection back to.
    if (!trigger || !triggerLabel || !fallback || !form
      || !fromDay || !fromMonth || !fromYear || !toDay || !toMonth || !toYear) {
      return;
    }

    const presetLinksRow = document.getElementById("date-preset-links");
    const presetAnchors = presetLinksRow
      ? Array.from(presetLinksRow.querySelectorAll("a[data-preset]"))
      : [];
    const activePreset = container.dataset.activePreset || "all_time";
    const latestDate = parseISODate(container.dataset.latestDate);

    let state = {
      start: parseDMYInputs(fromDay, fromMonth, fromYear),
      end: parseDMYInputs(toDay, toMonth, toYear),
    };
    const viewSeed = state.start || latestDate || new Date();
    let viewYear = viewSeed.getFullYear();
    let viewMonth = viewSeed.getMonth();

    // ---- build the panel shell once; renderCalendar() below repaints
    // just the two month grids on every click/hover/nav. ----
    const scrim = document.createElement("button");
    scrim.type = "button";
    scrim.className = "date-scrim";
    scrim.setAttribute("aria-label", "Close date range picker");

    const panel = document.createElement("div");
    panel.className = "date-panel";
    panel.id = "date-panel";
    panel.hidden = true;

    const presetsCol = document.createElement("div");
    presetsCol.className = "date-panel__presets";
    presetAnchors.forEach((a) => {
      const link = a.cloneNode(true);
      link.className = "date-panel__preset";
      if (link.dataset.preset === activePreset) link.classList.add("is-active");
      presetsCol.appendChild(link);
    });
    const customBtn = document.createElement("button");
    customBtn.type = "button";
    customBtn.className = "date-panel__preset";
    customBtn.textContent = "Custom range…";
    if (activePreset === "custom") customBtn.classList.add("is-active");
    presetsCol.appendChild(customBtn);

    const calendarSection = document.createElement("div");
    calendarSection.className = "date-panel__calendar";
    calendarSection.hidden = activePreset !== "custom";

    const monthsRow = document.createElement("div");
    monthsRow.className = "date-panel__months";
    calendarSection.appendChild(monthsRow);

    const footer = document.createElement("div");
    footer.className = "date-panel__footer";
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "button-secondary";
    cancelBtn.textContent = "Cancel";
    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "button-cta";
    applyBtn.textContent = "Apply";
    footer.appendChild(cancelBtn);
    footer.appendChild(applyBtn);
    calendarSection.appendChild(footer);

    panel.appendChild(presetsCol);
    panel.appendChild(calendarSection);
    container.appendChild(panel);
    document.body.appendChild(scrim);

    function chevronSvg(direction) {
      const d = direction === "prev" ? "M7 1L2 5l5 4" : "M3 1l5 4-5 4";
      return `<svg viewBox="0 0 9 10" fill="none" aria-hidden="true" focusable="false"><path d="${d}" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    }

    function renderMonth(year, monthIndex, position) {
      const wrap = document.createElement("div");
      wrap.className = `date-month date-month--${position}`;

      const head = document.createElement("div");
      head.className = "date-month__head";

      const prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "date-month__nav date-month__nav--prev";
      prevBtn.innerHTML = chevronSvg("prev");
      prevBtn.setAttribute("aria-label", "Previous month");
      prevBtn.addEventListener("click", () => {
        viewMonth -= 1;
        if (viewMonth < 0) {
          viewMonth = 11;
          viewYear -= 1;
        }
        renderCalendar();
      });

      const title = document.createElement("span");
      title.className = "date-month__title";
      title.textContent = `${MONTH_NAMES[monthIndex]} ${year}`;

      const nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "date-month__nav date-month__nav--next";
      nextBtn.innerHTML = chevronSvg("next");
      nextBtn.setAttribute("aria-label", "Next month");
      nextBtn.addEventListener("click", () => {
        viewMonth += 1;
        if (viewMonth > 11) {
          viewMonth = 0;
          viewYear += 1;
        }
        renderCalendar();
      });

      head.appendChild(prevBtn);
      head.appendChild(title);
      head.appendChild(nextBtn);
      wrap.appendChild(head);

      const table = document.createElement("table");
      table.className = "date-grid";
      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      WEEKDAY_LABELS.forEach((label) => {
        const th = document.createElement("th");
        th.textContent = label;
        headRow.appendChild(th);
      });
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      buildMonthWeeks(year, monthIndex).forEach((week) => {
        const row = document.createElement("tr");
        week.forEach((day) => {
          const td = document.createElement("td");
          td.className = "date-cell-wrap";
          if (day) {
            const isStart = sameDay(day, state.start);
            const previewEnd = state.start && !state.end ? state.hoverEnd : null;
            const bandEnd = state.end || previewEnd;
            if (sameDay(day, state.start)) td.classList.add("range-start");
            if (bandEnd && sameDay(day, bandEnd)) td.classList.add("range-end");
            if (inRange(day, state.start, bandEnd)) td.classList.add("in-range");

            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "date-cell";
            if (latestDate && sameDay(day, latestDate)) btn.classList.add("date-cell--latest");
            btn.textContent = String(day.getDate());
            btn.dataset.y = String(day.getFullYear());
            btn.dataset.m = String(day.getMonth());
            btn.dataset.d = String(day.getDate());
            btn.setAttribute(
              "aria-label",
              `${day.getDate()} ${MONTH_NAMES[day.getMonth()]} ${day.getFullYear()}`
            );
            btn.setAttribute("aria-pressed", String(isStart || sameDay(day, state.end)));
            td.appendChild(btn);
          }
          row.appendChild(td);
        });
        tbody.appendChild(row);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      return wrap;
    }

    function renderCalendar() {
      monthsRow.innerHTML = "";
      monthsRow.appendChild(renderMonth(viewYear, viewMonth, "first"));
      let secondYear = viewYear;
      let secondMonth = viewMonth + 1;
      if (secondMonth > 11) {
        secondMonth = 0;
        secondYear += 1;
      }
      monthsRow.appendChild(renderMonth(secondYear, secondMonth, "second"));
      applyBtn.disabled = !state.start;
    }

    monthsRow.addEventListener("click", (event) => {
      const cell = event.target.closest("button.date-cell");
      if (!cell) return;
      const clicked = new Date(
        Number(cell.dataset.y), Number(cell.dataset.m), Number(cell.dataset.d)
      );
      state = commitClick(state, clicked);
      state.hoverEnd = null;
      renderCalendar();
    });

    monthsRow.addEventListener("mouseover", (event) => {
      const cell = event.target.closest("button.date-cell");
      if (!cell || !state.start || state.end) return;
      state.hoverEnd = new Date(
        Number(cell.dataset.y), Number(cell.dataset.m), Number(cell.dataset.d)
      );
      renderCalendar();
    });

    function openPanel() {
      panel.hidden = false;
      scrim.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      container.classList.add("active");
      document.addEventListener("keydown", onKeydown);
      renderCalendar();
    }

    function closePanel() {
      panel.hidden = true;
      scrim.classList.remove("is-open");
      trigger.setAttribute("aria-expanded", "false");
      document.removeEventListener("keydown", onKeydown);
      // Re-seed from the live inputs -- discards any in-progress calendar
      // clicks that were never Applied, same as a Cancel.
      state = {
        start: parseDMYInputs(fromDay, fromMonth, fromYear),
        end: parseDMYInputs(toDay, toMonth, toYear),
      };
    }

    function onKeydown(event) {
      if (event.key === "Escape") {
        closePanel();
        trigger.focus();
      }
    }

    trigger.addEventListener("click", () => {
      if (panel.hidden) openPanel();
      else closePanel();
    });
    scrim.addEventListener("click", closePanel);

    customBtn.addEventListener("click", () => {
      presetsCol.querySelectorAll(".date-panel__preset").forEach((el) => el.classList.remove("is-active"));
      customBtn.classList.add("is-active");
      calendarSection.hidden = false;
      renderCalendar();
    });

    cancelBtn.addEventListener("click", closePanel);

    applyBtn.addEventListener("click", () => {
      if (!state.start) return;
      const end = state.end || state.start;
      writeDMYInputs(fromDay, fromMonth, fromYear, state.start);
      writeDMYInputs(toDay, toMonth, toYear, end);
      form.requestSubmit();
    });

    // Enhancement confirmed possible -- swap the raw fallback for the
    // trigger button now, not before (see the `hidden` attribute note on
    // the trigger in transactions.html).
    fallback.style.display = "none";
    trigger.hidden = false;
  });
})();

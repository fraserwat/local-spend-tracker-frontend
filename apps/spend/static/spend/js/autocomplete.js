// Progressive enhancement over the plain Recipient text input -- the form
// posts `q` and filters correctly with this script entirely absent (see
// TransactionFilterForm), so a fetch failure or JS error here just leaves
// the user with a plain search box, never a broken filter.
//
// Hand-rolled ARIA combobox (not a library) to the same shape GOV.UK's
// accessible-autocomplete uses: role="combobox" on the input,
// aria-activedescendant tracking the highlighted role="option", a
// role="listbox" popup. https://alphagov.github.io/accessible-autocomplete/
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("id_q");
  if (!input) return;
  const wrap = input.closest(".combobox-wrap");
  const suggestUrl = wrap && wrap.dataset.suggestUrl;
  if (!suggestUrl) return;

  const MIN_CHARS = 2;
  const DEBOUNCE_MS = 200;

  const listbox = document.createElement("div");
  listbox.className = "combobox-listbox";
  listbox.setAttribute("role", "listbox");
  listbox.id = "id_q_listbox";
  listbox.hidden = true;
  input.insertAdjacentElement("afterend", listbox);

  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", listbox.id);

  let options = [];
  let highlighted = -1;
  let debounceHandle = null;
  let fetchToken = 0;

  function close() {
    listbox.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    highlighted = -1;
  }

  function render(names) {
    options = names;
    highlighted = -1;
    listbox.innerHTML = "";
    if (!names.length) {
      close();
      return;
    }
    names.forEach((name, i) => {
      const opt = document.createElement("div");
      opt.className = "combobox-option";
      opt.setAttribute("role", "option");
      opt.id = `id_q_option_${i}`;
      opt.textContent = name;
      opt.addEventListener("mousedown", (event) => {
        // mousedown, not click -- fires before the input's blur handler,
        // so the selection lands before close() would otherwise run first.
        event.preventDefault();
        select(i);
      });
      listbox.appendChild(opt);
    });
    listbox.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function highlight(index) {
    const prev = listbox.querySelector(".combobox-option.highlighted");
    if (prev) prev.classList.remove("highlighted");
    highlighted = index;
    if (index < 0) {
      input.removeAttribute("aria-activedescendant");
      return;
    }
    const el = listbox.children[index];
    el.classList.add("highlighted");
    input.setAttribute("aria-activedescendant", el.id);
  }

  function select(index) {
    input.value = options[index];
    close();
  }

  function fetchSuggestions(q) {
    const token = ++fetchToken;
    fetch(`${suggestUrl}?q=${encodeURIComponent(q)}`)
      .then((res) => (res.ok ? res.json() : { results: [] }))
      .then((data) => {
        if (token !== fetchToken) return; // a newer keystroke already superseded this request
        render(data.results || []);
      })
      .catch(() => {
        /* network hiccup -- leave the plain input working, no error UI */
      });
  }

  input.addEventListener("input", () => {
    clearTimeout(debounceHandle);
    const q = input.value.trim();
    if (q.length < MIN_CHARS) {
      close();
      return;
    }
    debounceHandle = setTimeout(() => fetchSuggestions(q), DEBOUNCE_MS);
  });

  input.addEventListener("keydown", (event) => {
    if (listbox.hidden) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlight(Math.min(highlighted + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight(Math.max(highlighted - 1, 0));
    } else if (event.key === "Enter") {
      if (highlighted >= 0) {
        event.preventDefault();
        select(highlighted);
      }
    } else if (event.key === "Escape") {
      close();
    }
  });

  input.addEventListener("blur", close);
});

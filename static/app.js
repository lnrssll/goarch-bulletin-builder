// Small conveniences only: every page and form works without this file.

const unsaved = new Set();

document.addEventListener("input", (event) => {
  const form = event.target.closest("form[data-warn-unsaved]");
  if (form) unsaved.add(form);
});

window.addEventListener("beforeunload", (event) => {
  if (unsaved.size > 0) event.preventDefault();
});

// Ask before forms marked data-confirm, and disable buttons while a form is
// being sent so a slow download isn't started twice.
document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
    event.preventDefault();
    return;
  }
  unsaved.delete(form);
  for (const button of form.querySelectorAll("button")) {
    button.dataset.label = button.textContent;
    if (button.dataset.busy) button.textContent = button.dataset.busy;
    setTimeout(() => { button.disabled = true; });
  }
});

// The Back button can bring back a page with its buttons still disabled.
window.addEventListener("pageshow", () => {
  for (const button of document.querySelectorAll("button[data-label]")) {
    button.disabled = false;
    button.textContent = button.dataset.label;
  }
});

// Suggestion boxes: an input with a list="…" datalist gets a dropdown that
// matches as you type, completes on Tab, and lists everything when clicked.

const words = (text) => text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();

function suggestionsFrom(datalist) {
  return [...datalist.options].map((option) => ({
    value: option.value,
    detail: option.textContent.trim(),
    names: [option.value, ...JSON.parse(option.dataset.also || "[]")].map(words),
    data: option.dataset,
  }));
}

function rank(suggestion, typed) {
  let best = Infinity;
  suggestion.names.forEach((name, index) => {
    const alias = index > 0 ? 1 : 0;
    if (name.startsWith(typed)) best = Math.min(best, alias);
    else if (` ${name}`.includes(` ${typed}`)) best = Math.min(best, 2 + alias);
  });
  return best;
}

let boxCount = 0;

function makeSuggestionBox(input) {
  const suggestions = suggestionsFrom(document.getElementById(input.getAttribute("list")));
  const box = document.createElement("ul");
  box.id = `suggestions-${++boxCount}`;
  box.className = "suggestions";
  box.setAttribute("role", "listbox");
  box.hidden = true;
  box.addEventListener("mousedown", (event) => event.preventDefault());
  const holder = input.closest(".prefixed") || input.parentElement;
  holder.classList.add("has-suggestions");
  holder.append(box);

  input.removeAttribute("list");
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-controls", box.id);

  let shown = [];
  let active = -1;

  function highlight(index) {
    active = index;
    [...box.children].forEach((item, i) => item.setAttribute("aria-selected", String(i === active)));
    const item = box.children[active];
    if (item) {
      input.setAttribute("aria-activedescendant", item.id);
      item.scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function close() {
    box.hidden = true;
    shown = [];
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function open(everything) {
    const typed = words(input.value);
    shown = everything || !typed
      ? suggestions
      : suggestions
          .map((suggestion) => ({ suggestion, rank: rank(suggestion, typed) }))
          .filter((match) => match.rank < Infinity)
          .sort((a, b) => a.rank - b.rank)
          .map((match) => match.suggestion);
    if (shown.length === 0 || (!everything && !typed)) return close();

    box.replaceChildren(...shown.map((suggestion, index) => {
      const item = document.createElement("li");
      item.id = `${box.id}-${index}`;
      item.setAttribute("role", "option");
      item.textContent = suggestion.value;
      if (suggestion.detail) {
        const detail = document.createElement("small");
        detail.textContent = suggestion.detail;
        item.append(detail);
      }
      item.addEventListener("click", () => pick(suggestion));
      return item;
    }));
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
    highlight(everything ? shown.findIndex((suggestion) => suggestion.value === input.value) : 0);
  }

  function pick(suggestion) {
    close();
    input.value = suggestion.value;
    delete input.dataset.autofilled;
    input.dispatchEvent(new CustomEvent("suggestion-picked", { bubbles: true, detail: suggestion }));
    changed(input);
  }

  input.addEventListener("input", () => open(false));
  input.addEventListener("click", () => open(true));
  input.addEventListener("blur", close);
  input.addEventListener("keydown", (event) => {
    const isOpen = !box.hidden;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (isOpen) highlight(Math.min(active + 1, shown.length - 1));
      else open(true);
    } else if (event.key === "ArrowUp" && isOpen) {
      event.preventDefault();
      highlight(Math.max(active - 1, 0));
    } else if (event.key === "Enter" && isOpen && active >= 0) {
      event.preventDefault();
      pick(shown[active]);
    } else if (event.key === "Tab" && isOpen && active >= 0) {
      pick(shown[active]);
    } else if (event.key === "Escape" && isOpen) {
      event.preventDefault();
      close();
    }
  });

  return suggestions;
}

// A fixed "Fr." or "p." in front of a box, hidden for "Reader Service",
// "Handout" and the like: the server adds the prefix only where it belongs.
function updatePrefix(input) {
  const holder = input.closest(".prefixed");
  if (!holder) return;
  const value = input.value.trim().toLowerCase();
  let shown = true;
  if ("prefixForNumbers" in holder.dataset) shown = value === "" || /^\d/.test(value);
  if (holder.dataset.prefixUnless) {
    shown = !JSON.parse(holder.dataset.prefixUnless).some((word) => word.toLowerCase() === value);
  }
  holder.classList.toggle("no-prefix", !shown);
}

function changed(field) {
  updatePrefix(field);
  if (field.form && "warnUnsaved" in field.form.dataset) unsaved.add(field.form);
}

// Filling in the rest of a hymn row. An empty box, or one filled in here
// before, is filled. What the page was loaded with (a saved hymn, or the
// "Example" row's page 0) belonged to the title as it was, so a known value
// replaces it, but nothing erases it. Anything typed or picked here is kept.
function autofill(field, value) {
  const loaded = "loaded" in field.dataset && value;
  if (field.value !== "" && !("autofilled" in field.dataset) && !loaded) return;
  delete field.dataset.loaded;
  field.value = value || "";
  if (value) field.dataset.autofilled = "";
  else delete field.dataset.autofilled;
  changed(field);
}

function setUpHymnRows(hymns) {
  const byName = new Map();
  for (const hymn of hymns) {
    for (const name of hymn.names) if (!byName.has(name)) byName.set(name, hymn);
  }
  const hymnIn = (row) => byName.get(words(row.querySelector("[name=hymn_title]").value));
  const pageFor = (hymn, mode) => hymn?.data.page || JSON.parse(hymn?.data.pages || "{}")[mode];
  for (const field of document.querySelectorAll("[name=hymn_mode], [name=hymn_page]")) {
    if (field.value !== "") field.dataset.loaded = "";
  }

  document.addEventListener("change", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    const mode = row.querySelector("[name=hymn_mode]");
    const page = row.querySelector("[name=hymn_page]");
    if (event.target.name === "hymn_title") {
      const hymn = hymnIn(row);
      autofill(mode, hymn?.data.mode);
      autofill(page, pageFor(hymn, mode.value));
    } else if (event.target === mode) {
      delete mode.dataset.autofilled;
      delete mode.dataset.loaded;
      const hymn = hymnIn(row);
      if (hymn?.data.pages) autofill(page, pageFor(hymn, mode.value));
    }
  });
  document.addEventListener("suggestion-picked", (event) => {
    if (event.target.name === "hymn_title") {
      event.target.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });
}

document.addEventListener("input", (event) => {
  delete event.target.dataset.autofilled;
  delete event.target.dataset.loaded;
  updatePrefix(event.target);
});

for (const input of document.querySelectorAll(".prefixed input")) updatePrefix(input);

let hymnSuggestions = [];
for (const input of document.querySelectorAll("input[list]")) {
  const suggestions = makeSuggestionBox(input);
  if (input.name === "hymn_title") hymnSuggestions = suggestions;
}
if (hymnSuggestions.length > 0) setUpHymnRows(hymnSuggestions);

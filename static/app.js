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

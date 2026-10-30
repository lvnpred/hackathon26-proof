// Enter or Space on the row itself opens it (Space is stopped from scrolling the page).
export function opensOnKey(event) {
  if ((event.key !== "Enter" && event.key !== " ") || event.target !== event.currentTarget) return false;
  event.preventDefault();
  return true;
}

// A click on a row opens it, unless it landed on one of the row's own controls.
export const opensRow = (target) => !target.closest("a, button, input, textarea, select, label");

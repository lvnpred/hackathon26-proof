// A click on a row opens it, unless it landed on one of the row's own controls.
export const opensRow = (target) => !target.closest("a, button, input, textarea, select, label");

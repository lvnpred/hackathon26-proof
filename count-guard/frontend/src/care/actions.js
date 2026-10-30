// Which action buttons the doctor's bar offers, and which panels are open.
export const ACTIONS = {
  clinic: [["orders", "Dictate orders"], ["photo", "Reference photo"]],
  ward: [["orders", "Dictate orders"], ["photo", "Wound photo"], ["discharge", "Dictate discharge"]],
};

export const actionsFor = (state) => ACTIONS[state] || [];

export function toggled(set, id) {
  const next = new Set(set);
  if (!next.delete(id)) next.add(id);
  return next;
}

const DRAFT_FOR = { orders: "order", discharge: "discharge" };

// A dictated draft is never hidden: an open draft opens its panel.
export function panelOpen(chosen, id, view) {
  return chosen.has(id) || Boolean(DRAFT_FOR[id] && view?.drafts?.[DRAFT_FOR[id]]);
}

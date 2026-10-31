import { useState } from "react";
import { FIELD_LABEL } from "./inspect.js";
import { CHIP_INPUT, chipEdit, chipValid, chipValue, orderSentence, rowItem } from "./orders.js";

// One drafted order as chips. Tapping a chip opens an input for that field; Enter or blur commits, Esc cancels.
export default function OrderSentence({ row, index, onChange }) {
  const [editing, setEditing] = useState(null);
  const [value, setValue] = useState("");
  const [problem, setProblem] = useState("");
  const chips = row.text.trim() ? orderSentence(rowItem(row)) : [{ field: "text", text: "Add order text" }];

  function open(field) {
    setEditing(field);
    setValue(chipValue(row, field));
    setProblem("");
  }
  function commit(field, next) {
    if (!chipValid(field, next)) {
      setProblem(`${FIELD_LABEL[field]} must be a number.`);
      return false;
    }
    onChange(chipEdit(row, field, next));
    setEditing(null);
    setProblem("");
    return true;
  }
  const cancel = () => {
    setEditing(null);
    setProblem("");
  };
  const label = (field) => `${FIELD_LABEL[field]} of order ${index + 1}`;

  return (
    <div className="row order-sentence">
      {chips.map((chip, i) => {
        const dot = i > 0 && <span aria-hidden="true" className="muted"> · </span>;
        if (chip.field !== editing) {
          return <span key={chip.field}>{dot}<button type="button" className="chip" onClick={() => open(chip.field)}>{chip.text}</button></span>;
        }
        const keys = {
          onKeyDown: (e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(chip.field, e.target.value); }
            if (e.key === "Escape") cancel();
          },
          // A bad number stays open with its message; anything else commits on blur.
          onBlur: (e) => { if (!commit(chip.field, e.target.value)) e.target.focus(); },
        };
        return CHIP_INPUT[chip.field] === "select" ? (
          <select key={chip.field} autoFocus aria-label={label(chip.field)} value={value} onChange={(e) => setValue(e.target.value)} {...keys}>
            <option value="none">none</option>
            <option value="photo">photo</option>
            <option value="video">video</option>
          </select>
        ) : (
          <input key={chip.field} autoFocus aria-label={label(chip.field)} value={value} onChange={(e) => setValue(e.target.value)} {...keys} />
        );
      })}
      {problem && <span className="error small" role="alert">{problem}</span>}
    </div>
  );
}

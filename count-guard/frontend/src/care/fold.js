// Phone chrome: which header controls hide behind "Demo controls". The patient keeps the doctor's status chip.
export function foldsOnPhone(control, role) {
  return !(control === "doctor" && role === "patient");
}

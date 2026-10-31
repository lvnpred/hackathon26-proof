// The people the product knows are signed in. The demo role switch picks one; the patient has no staff sign-in.
export const SIGNED_IN = {
  doctor: { name: "Dr. A. Rao", role: "Doctor" },
  nurse: { name: "Nurse Meena", role: "Ward nurse" },
};

// "Dr. A. Rao" -> "AR", "Nurse Meena" -> "NM": the first letter of the first and last words, skipping the "Dr." title.
export function initials(name) {
  const words = name.replace(/^Dr\.?\s+/i, "").split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  const first = words[0][0];
  if (words.length === 1) return first.toUpperCase();
  return (first + words[words.length - 1][0]).toUpperCase();
}

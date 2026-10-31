export const STRIP_TEXT = "Research demo · Synthetic data · Not for clinical use";

// The product's own safety notice: first on every page, at every width.
export default function ProductStrip() {
  return <p className="product-strip" role="note">{STRIP_TEXT}</p>;
}

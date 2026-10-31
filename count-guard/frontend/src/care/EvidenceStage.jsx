import { useEffect, useRef } from "react";
import { drawItems, isDense, isFocus, isFocusRegion, labelKind, nudgeLabels } from "./evidence.js";

// Draw boxes (normalised [x, y, w, h]) over the image's displayed size. Kept: solid colour. Ignored: dashed grey.
// A white outer stroke keeps a box visible on any picture. The inline picture labels each box with a small id tag;
// the expanded view uses full pills, nudged clear of each other, unless they would crowd. With a `focus` pick,
// the other boxes are dimmed.
function draw(canvas, img, { boxes, regions, labels, rows, expanded, focus }) {
  if (!canvas || !img) return;
  const w = img.clientWidth;
  const h = img.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext?.("2d");
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const scale = Math.min(1, w / 640);
  const FONT = Math.max(10, Math.round(12 * scale));
  ctx.font = `${FONT}px sans-serif`;
  const items = drawItems(boxes, regions, rows);
  const alpha = (it) => {
    if (it.region != null) return isFocusRegion(it.region, focus) ? 1 : 0.25;
    return it.box && focus?.region == null && !isFocus(it.box, focus) ? 0.25 : 1;
  };
  for (const it of items) {
    const [x, y, bw, bh] = it.bbox;
    ctx.globalAlpha = alpha(it);
    ctx.setLineDash([]);
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 4;
    ctx.strokeRect(x * w, y * h, bw * w, bh * h);
    ctx.strokeStyle = it.colour;
    ctx.lineWidth = 2;
    ctx.setLineDash(it.dashed ? [4, 3] : []);
    ctx.strokeRect(x * w, y * h, bw * w, bh * h);
  }
  ctx.globalAlpha = 1;
  if (!labels) return;
  const dense = isDense(items.filter((it) => it.box).map((it) => ({ pill: ctx.measureText(it.text).width + 8, box: it.bbox[2] * w })));
  const kinds = items.map((it) => (it.box ? labelKind(it.box, { expanded, dense, focus }) : "full"));
  const PH = FONT + 4;
  const full = items.filter((_, i) => kinds[i] === "full");
  const placed = nudgeLabels(full.map((it) => ({ x: Math.min(it.bbox[0] * w, w - 20), y: Math.max(it.bbox[1] * h - PH - 2, 0), w: ctx.measureText(it.text).width + 8, h: PH })));
  // Keep every pill inside the canvas on the right and at the bottom (T7-2).
  const pills = placed.map((p) => ({ ...p, x: Math.max(0, Math.min(p.x, w - p.w)), y: Math.max(0, Math.min(p.y, h - p.h)) }));
  ctx.setLineDash([]);
  ctx.textBaseline = "middle";
  let n = 0;
  items.forEach((it, i) => {
    ctx.globalAlpha = alpha(it);
    if (kinds[i] === "tag") {
      const text = String(it.box.id);
      const tw = ctx.measureText(text).width + 6;
      const th = FONT + 2;
      ctx.fillStyle = it.colour;
      ctx.fillRect(it.bbox[0] * w, it.bbox[1] * h, tw, th);
      ctx.fillStyle = "#fff";
      ctx.fillText(text, it.bbox[0] * w + 3, it.bbox[1] * h + th / 2 + 0.5);
      return;
    }
    const p = pills[n];
    n += 1;
    ctx.fillStyle = it.colour;
    ctx.fillRect(p.x, p.y, p.w, p.h);
    ctx.fillStyle = "#fff";
    ctx.fillText(it.text, p.x + 4, p.y + PH / 2 + 0.5);
  });
  ctx.globalAlpha = 1;
}

export function Stage({ image, boxes, regions, labels = true, rows, expanded = false, focus = null, ...rest }) {
  const img = useRef(null);
  const canvas = useRef(null);
  const paint = useRef(null);
  paint.current = () => draw(canvas.current, img.current, { boxes, regions, labels, rows, expanded, focus });
  useEffect(() => {
    const again = () => paint.current();
    window.addEventListener("resize", again);
    return () => window.removeEventListener("resize", again);
  }, []);
  useEffect(() => paint.current());
  return (
    <div {...rest}>
      <img ref={img} src={image?.url} alt="Evidence frame" onLoad={() => paint.current()} />
      <canvas ref={canvas} aria-hidden="true" />
    </div>
  );
}

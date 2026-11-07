// Subtle 3D: stat tiles tilt a few degrees toward the pointer and catch a moving highlight.
// Deliberately limited to tiles that only show a headline number. Anything with a table, a chart
// or live-ticking rows stays still, so nothing moves under the user's eyes while they read.

const MAX_DEG = 5;
let frame = 0;
let current: HTMLElement | null = null;

function isTile(card: HTMLElement): boolean {
  if (card.classList.contains("pass")) return true;
  // Anything the user reads or edits in place stays still: tables, charts, forms, and tall panels.
  if (card.querySelector("table, canvas, svg.recharts-surface, .recharts-wrapper, input, textarea, select, form, pre")) return false;
  return card.offsetHeight <= 380;
}

function reset(el: HTMLElement | null): void {
  if (!el) return;
  el.style.setProperty("--rx", "0deg");
  el.style.setProperty("--ry", "0deg");
  el.style.setProperty("--glare", "0");
}

function onMove(e: PointerEvent): void {
  if (e.pointerType === "touch") return;
  const card = (e.target as Element | null)?.closest?.<HTMLElement>(".card, .pass");
  if (!card || !isTile(card)) {
    if (current) {
      reset(current);
      current = null;
    }
    return;
  }
  if (current && current !== card) reset(current);
  current = card;
  card.setAttribute("data-tilt", "");
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(() => {
    const r = card.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    card.style.setProperty("--ry", `${((px - 0.5) * 2 * MAX_DEG).toFixed(2)}deg`);
    card.style.setProperty("--rx", `${((0.5 - py) * 2 * MAX_DEG).toFixed(2)}deg`);
    card.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
    card.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
    card.style.setProperty("--glare", "1");
  });
}

/** Install once at startup. A no-op when the user prefers reduced motion. */
export function installTilt(): () => void {
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return () => undefined;
  document.addEventListener("pointermove", onMove, { passive: true });
  const leave = () => {
    reset(current);
    current = null;
  };
  document.documentElement.addEventListener("pointerleave", leave);
  return () => {
    document.removeEventListener("pointermove", onMove);
    document.documentElement.removeEventListener("pointerleave", leave);
    cancelAnimationFrame(frame);
  };
}

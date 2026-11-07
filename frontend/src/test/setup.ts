// Browser APIs that jsdom lacks but the Astryx components use.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

class NoopObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): unknown[] {
    return [];
  }
}
for (const name of ["ResizeObserver", "IntersectionObserver"] as const) {
  if (!(name in window)) {
    (window as unknown as Record<string, unknown>)[name] = NoopObserver;
  }
}
if (!Element.prototype.scrollTo) Element.prototype.scrollTo = () => undefined;
if (typeof CSS === "undefined" || !CSS.escape) {
  (globalThis as unknown as { CSS: { escape: (s: string) => string } }).CSS = {
    escape: (s: string) => s.replace(/[^a-zA-Z0-9_-]/g, "\$&"),
  };
}
if (typeof HTMLDialogElement !== "undefined" && !HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.show = HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

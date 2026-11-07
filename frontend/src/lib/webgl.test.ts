import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { disposeRenderer, resetWebglProbe, webglAvailable } from "./webgl";

describe("webglAvailable", () => {
  const loseContext = vi.fn();
  let getContext: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    resetWebglProbe();
    loseContext.mockClear();
    getContext = vi.fn(() => ({ getExtension: (n: string) => (n === "WEBGL_lose_context" ? { loseContext } : null) }));
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(getContext as never);
  });
  afterEach(() => vi.restoreAllMocks());

  it("probes once and caches, so mounting many 3D components does not open a context each", () => {
    expect(webglAvailable()).toBe(true);
    expect(webglAvailable()).toBe(true);
    expect(webglAvailable()).toBe(true);
    expect(getContext).toHaveBeenCalledTimes(1);
  });

  it("releases the probe context instead of leaving it for the garbage collector", () => {
    webglAvailable();
    expect(loseContext).toHaveBeenCalledTimes(1);
  });

  it("is false when no context can be created", () => {
    resetWebglProbe();
    getContext.mockReturnValue(null);
    expect(webglAvailable()).toBe(false);
  });
});

describe("disposeRenderer", () => {
  it("frees the GPU context, not just the three.js objects", () => {
    const order: string[] = [];
    const remove = vi.fn(() => order.push("remove"));
    const renderer = {
      forceContextLoss: () => order.push("forceContextLoss"),
      dispose: () => order.push("dispose"),
      domElement: { remove },
    };
    disposeRenderer(renderer as never);
    expect(order).toEqual(["forceContextLoss", "dispose", "remove"]);
  });
});

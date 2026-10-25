import { describe, expect, it } from "vitest";

import { isDesktop, notifyRunFinished, routeForDeepLink } from "./desktop";

describe("routeForDeepLink", () => {
  it("maps aletheia://run/<id> to the run page", () => {
    expect(routeForDeepLink("aletheia://run/abc-123")).toBe("/runs/abc-123");
    expect(routeForDeepLink("aletheia://run/abc-123/")).toBe("/runs/abc-123");
  });

  it("rejects other schemes, unknown targets and unsafe ids", () => {
    expect(routeForDeepLink("https://run/abc")).toBeNull();
    expect(routeForDeepLink("aletheia://settings")).toBeNull();
    expect(routeForDeepLink("aletheia://run/")).toBeNull();
    expect(routeForDeepLink("aletheia://run/..%2F..%2Fx")).toBeNull();
    expect(routeForDeepLink("not a url")).toBeNull();
  });
});

describe("browser fallback", () => {
  it("is not the desktop shell and notifying is a harmless no-op", async () => {
    expect(isDesktop()).toBe(false);
    await expect(notifyRunFinished("abc", "completed")).resolves.toBeUndefined();
  });
});

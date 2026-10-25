import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { applyTheme, resolveTheme, setTheme } from "./theme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});
afterEach(() => vi.unstubAllGlobals());

describe("theme", () => {
  it("defaults to dark when nothing is stored and the OS has no preference", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    expect(resolveTheme()).toBe("dark");
  });

  it("follows the OS light preference until the user chooses", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    expect(resolveTheme()).toBe("light");
    setTheme("dark");
    expect(resolveTheme()).toBe("dark");
  });

  it("setTheme persists and sets the data attribute", () => {
    setTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("aletheia_theme")).toBe("light");
  });

  it("ignores a corrupt stored value", () => {
    localStorage.setItem("aletheia_theme", "neon");
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    expect(resolveTheme()).toBe("dark");
    applyTheme("dark");
  });
});

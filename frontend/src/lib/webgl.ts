import type { WebGLRenderer } from "three";

let probed: boolean | null = null;

/**
 * Whether WebGL works here. The answer is cached and the probe context is released: every call
 * used to open a fresh context that was never freed, and the browser keeps only ~16 alive, so
 * after a few page changes it started killing the oldest ones, which left blank (white) canvases.
 */
export function webglAvailable(): boolean {
  if (probed !== null) return probed;
  try {
    const canvas = document.createElement("canvas");
    const gl = (canvas.getContext("webgl2") || canvas.getContext("webgl")) as WebGLRenderingContext | null;
    probed = !!gl;
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
  } catch {
    probed = false;
  }
  return probed;
}

/** test hook */
export function resetWebglProbe(): void {
  probed = null;
}

/** Tear a renderer down for good. `dispose()` alone leaves the GPU context alive until GC. */
export function disposeRenderer(renderer: WebGLRenderer): void {
  renderer.forceContextLoss();
  renderer.dispose();
  renderer.domElement.remove();
}

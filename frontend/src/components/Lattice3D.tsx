import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { disposeRenderer, webglAvailable } from "../lib/webgl";

export type LatticeVariant = "wave" | "ripple" | "ridge" | "steps" | "bars";

const N = 22;

function cssColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** Height 0..1 for a cell at (x, z) in [-1, 1] at time t. */
function field(v: LatticeVariant, x: number, z: number, t: number, i: number): number {
  switch (v) {
    case "ripple": {
      const r = Math.hypot(x, z);
      return 0.5 + 0.5 * Math.sin(8 * r - t * 1.8) * Math.max(0, 1 - r * 0.55);
    }
    case "ridge":
      return 0.12 + 0.88 * Math.abs(Math.sin(2.2 * x + t * 0.45)) * (1 - Math.abs(z) * 0.55) * (0.7 + 0.3 * Math.sin(3 * z + t * 0.3));
    case "steps": {
      const raw = 0.5 + 0.5 * Math.sin(2.6 * x + t * 0.6) * Math.sin(2.6 * z - t * 0.5);
      return Math.max(0.08, Math.floor(raw * 5) / 5);
    }
    case "bars":
      return 0.18 + 0.82 * Math.pow(0.5 + 0.5 * Math.sin(t * 0.9 + i * 1.713), 2);
    default:
      return 0.5 + 0.5 * Math.sin(3 * x + t * 0.9) * Math.cos(3 * z - t * 0.7);
  }
}

/**
 * A decorative field of blocks whose heights roll over time, coloured in flat bands from ember
 * to amber. It leans toward the pointer and stops when off screen. Purely ornamental; it carries
 * no data, so it is hidden from assistive tech.
 */
export default function Lattice3D({ variant = "wave" }: { variant?: LatticeVariant }) {
  const host = useRef<HTMLDivElement>(null);
  const [supported] = useState(webglAvailable);

  useEffect(() => {
    const el = host.current;
    if (!el || !supported) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    const bands = [
      new THREE.Color(cssColor("--bg-elevated", "#1a1a1a")),
      new THREE.Color("#5a0f09"),
      new THREE.Color(cssColor("--accent", "#ff2b1c")),
      new THREE.Color(cssColor("--accent-2", "#ff7a00")),
      new THREE.Color("#ffb020"),
    ];

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.style.display = "block";
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 80);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(4, 8, 3);
    scene.add(key);

    const geo = new THREE.BoxGeometry(0.34, 1, 0.34);
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.6, metalness: 0.05 });
    const mesh = new THREE.InstancedMesh(geo, mat, N * N);
    mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(N * N * 3), 3);
    const group = new THREE.Group();
    group.add(mesh);
    scene.add(group);

    const dummy = new THREE.Object3D();
    const span = 8;
    const cellX: number[] = [];
    const cellZ: number[] = [];
    for (let zi = 0; zi < N; zi++) {
      for (let xi = 0; xi < N; xi++) {
        cellX.push((xi / (N - 1)) * 2 - 1);
        cellZ.push((zi / (N - 1)) * 2 - 1);
      }
    }

    const draw = (t: number) => {
      for (let i = 0; i < N * N; i++) {
        const h = field(variant, cellX[i], cellZ[i], t, i);
        const height = 0.08 + h * 2.4;
        dummy.position.set(cellX[i] * (span / 2), height / 2, cellZ[i] * (span / 2));
        dummy.scale.set(1, height, 1);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
        mesh.setColorAt(i, bands[Math.min(bands.length - 1, Math.floor(h * bands.length))]);
      }
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    };
    draw(0);

    const pointer = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1;
    };
    const onLeave = () => (pointer.x = pointer.y = 0);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    const resize = () => {
      const w = el.clientWidth || 600;
      const h = el.clientHeight || 220;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = `${w}px`;
      renderer.domElement.style.height = `${h}px`;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf = 0;
    let visible = true;
    const t0 = performance.now();
    let frame = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      const t = (now - t0) / 1000;
      if (!reduced && frame++ % 2 === 0) draw(t); // half rate: plenty smooth for a backdrop
      group.rotation.y = reduced ? 0.6 : 0.6 + Math.sin(t * 0.15) * 0.25 + pointer.x * 0.25;
      camera.position.set(0, 7.4 + pointer.y * 0.6, 14.5);
      camera.lookAt(0, 0.2, 0);
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(loop);
    const io = new IntersectionObserver(([en]) => (visible = en.isIntersecting), { threshold: 0.01 });
    io.observe(el);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      geo.dispose();
      mat.dispose();
      mesh.dispose();
      disposeRenderer(renderer);
    };
  }, [variant, supported]);

  if (!supported) return null;
  return <div ref={host} className="lattice3d" aria-hidden="true" />;
}

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { disposeRenderer, webglAvailable } from "../lib/webgl";

interface Props {
  /** 0..1, or null when there is no reading yet */
  value: number | null;
  /** value below which the lit ticks turn red */
  warnBelow?: number;
}

const TICKS = 36;
const SWEEP = Math.PI * 1.5; // 270 degrees

function cssColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/**
 * A dial built from flat blocks: a ring of tick blocks that light up to the reading and a needle
 * that swings to it. The whole instrument tilts toward the pointer and bobs gently. Reading is
 * passed through a ref, so a new value animates the needle instead of rebuilding the scene.
 */
export default function Gauge3D({ value, warnBelow = 0.4 }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [supported] = useState(webglAvailable);
  const reading = useRef(value);
  reading.current = value;

  useEffect(() => {
    const el = host.current;
    if (!el || !supported) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const orange = new THREE.Color(cssColor("--accent-2", "#ff7a00"));
    const red = new THREE.Color(cssColor("--accent", "#ff2b1c"));
    const off = new THREE.Color(cssColor("--bg-elevated", "#1a1a1a"));
    const base = new THREE.Color(cssColor("--bg-card-hover", "#151515"));

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.style.display = "block";
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 50);
    camera.position.set(0, 0.2, 6);
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 2);
    key.position.set(2, 3, 5);
    scene.add(key);

    const rig = new THREE.Group();
    scene.add(rig);

    const disc = new THREE.Mesh(
      new THREE.CylinderGeometry(1.75, 1.75, 0.18, 64),
      new THREE.MeshStandardMaterial({ color: base, roughness: 0.9 }),
    );
    disc.rotation.x = Math.PI / 2;
    disc.position.z = -0.12;
    rig.add(disc);

    const ticks: THREE.Mesh[] = [];
    const startAngle = Math.PI * 1.25; // lower left, sweeping clockwise over the top
    for (let i = 0; i < TICKS; i++) {
      const t = i / (TICKS - 1);
      const a = startAngle - t * SWEEP;
      const big = i % 5 === 0;
      const m = new THREE.Mesh(
        new THREE.BoxGeometry(0.07, big ? 0.32 : 0.22, 0.12),
        new THREE.MeshStandardMaterial({ color: off, roughness: 0.6 }),
      );
      m.position.set(Math.cos(a) * 1.42, Math.sin(a) * 1.42, 0.02);
      m.rotation.z = a - Math.PI / 2;
      rig.add(m);
      ticks.push(m);
    }

    const needle = new THREE.Group();
    const blade = new THREE.Mesh(
      new THREE.BoxGeometry(0.07, 1.25, 0.08),
      new THREE.MeshStandardMaterial({ color: 0xf4f1ee, roughness: 0.4 }),
    );
    blade.position.y = 0.55;
    needle.add(blade);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.2, 24), new THREE.MeshStandardMaterial({ color: red, roughness: 0.5 }));
    hub.rotation.x = Math.PI / 2;
    needle.add(hub);
    needle.position.z = 0.12;
    rig.add(needle);

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
      const w = el.clientWidth || 260;
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

    let shown = 0; // needle position, 0..1
    let raf = 0;
    let visible = true;
    const t0 = performance.now();
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      const t = (now - t0) / 1000;
      const v = reading.current;
      const target = v === null ? 0 : Math.min(1, Math.max(0, v));
      shown += (target - shown) * (reduced ? 1 : 0.06);
      // the needle starts at the lower-left tick and sweeps clockwise
      needle.rotation.z = startAngle - shown * SWEEP - Math.PI / 2;
      const lit = v === null ? 0 : Math.round(shown * (TICKS - 1));
      const warn = v !== null && v < warnBelow;
      ticks.forEach((m, i) => {
        const mat = m.material as THREE.MeshStandardMaterial;
        mat.color.lerp(i <= lit && v !== null ? (warn ? red : orange) : off, reduced ? 1 : 0.2);
        const pop = i === lit && v !== null && !reduced ? 1 + 0.25 * Math.sin(t * 6) : 1;
        m.scale.set(1, pop, 1);
      });
      if (!reduced) {
        rig.rotation.y += (pointer.x * 0.5 - rig.rotation.y) * 0.08;
        rig.rotation.x += (pointer.y * 0.3 - rig.rotation.x) * 0.08;
        rig.position.y = 0.05 * Math.sin(t * 1.2);
      }
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
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose?.();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => x.dispose());
      });
      disposeRenderer(renderer);
    };
  }, [supported, warnBelow]);

  if (!supported) return null;
  return (
    <div
      ref={host}
      className="gauge3d"
      data-testid="gauge3d"
      role="img"
      aria-label={value === null ? "No reading yet" : `Reading ${(value * 100).toFixed(0)} percent`}
    />
  );
}

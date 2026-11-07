import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { disposeRenderer, webglAvailable } from "../lib/webgl";

export interface Slice {
  name: string;
  value: number;
}

interface Props {
  slices: Slice[];
}

// Plain geometry only: flat-shaded boxes under real lights. No gradient textures.
const MAX_SLABS = 12;
const SLAB = 0.46;
const GAP = 0.2;
const MAX_H = 1.7;
const CONCENTRATED = 0.25; // a position above this share of the book is drawn in the alert colour

function cssColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function label(text: string, color: string): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 64;
  const ctx = c.getContext("2d")!;
  ctx.font = "700 30px 'Geist Mono Variable', monospace";
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 128, 32);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
  s.scale.set(0.8, 0.2, 1);
  return s;
}

const easeOut = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 4);

/**
 * The book as a plinth of slabs: footprint is equal, height is the position's share of market
 * value. Slabs rise in one after another, the whole thing turns slowly, and the camera leans
 * toward the pointer. With no data it shows ghost wireframes, labelled as a preview.
 */
export default function HoldingsObject3D({ slices }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [supported] = useState(webglAvailable);
  const [hover, setHover] = useState<{ name: string; pct: number } | null>(null);
  const [themeTick, setThemeTick] = useState(0);
  const ghost = slices.length === 0;

  useEffect(() => {
    const obs = new MutationObserver(() => setThemeTick((t) => t + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const el = host.current;
    if (!el || !supported) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

    const orange = new THREE.Color(cssColor("--accent-2", "#ff7a00"));
    const red = new THREE.Color(cssColor("--accent", "#ff2b1c"));
    const base = new THREE.Color(cssColor("--bg-elevated", "#1a1a1a"));
    const line = new THREE.Color(cssColor("--border-medium", "#333333"));
    const text = cssColor("--text-secondary", "#a39d98");

    const data: Slice[] = ghost
      ? [4, 7, 3, 9, 5, 2, 6].map((v, i) => ({ name: `·${i + 1}`, value: v }))
      : [...slices].sort((a, b) => b.value - a.value).slice(0, MAX_SLABS);
    const total = data.reduce((s, d) => s + d.value, 0) || 1;
    const top = Math.max(...data.map((d) => d.value)) || 1;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.style.display = "block";
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 60);
    camera.position.set(2.9, 2.5, 3.5);

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(3, 6, 2);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(-4, 2, -3);
    scene.add(fill);

    const cols = Math.min(4, Math.ceil(Math.sqrt(data.length)));
    const rows = Math.ceil(data.length / cols);
    const pitch = SLAB + GAP;
    const worldW = cols * pitch;
    const worldD = rows * pitch;

    const group = new THREE.Group();
    scene.add(group);

    // plinth
    const plinth = new THREE.Mesh(
      new THREE.BoxGeometry(worldW + 0.5, 0.12, worldD + 0.5),
      new THREE.MeshStandardMaterial({ color: base, roughness: 0.9, metalness: 0 }),
    );
    plinth.position.y = -0.06;
    group.add(plinth);

    // a floor grid that runs past the plinth, an orbit ring, and drifting dust: depth cues, all flat
    const grid = new THREE.GridHelper(9, 18, line, line);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.35;
    grid.position.y = -0.13;
    scene.add(grid);
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(Math.max(worldW, worldD) * 0.95 + 0.6, 0.012, 8, 120),
      new THREE.MeshBasicMaterial({ color: red }),
    );
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.02;
    scene.add(ring);
    const dustN = 70;
    const dustPos = new Float32Array(dustN * 3);
    const dustSeed = Array.from({ length: dustN }, (_, i) => ({ a: (i * 2.399) % (Math.PI * 2), r: 1.4 + ((i * 37) % 100) / 100 * 2.2, y: ((i * 53) % 100) / 100 * 2.6, s: 0.2 + ((i * 17) % 10) / 40 }));
    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
    const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({ color: orange, size: 0.035, sizeAttenuation: true }));
    scene.add(dust);

    const slabs: { mesh: THREE.Mesh; h: number; delay: number; name: string; pct: number; tag: THREE.Sprite }[] = [];
    data.forEach((d, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const share = d.value / total;
      const h = Math.max(0.12, (d.value / top) * MAX_H);
      const concentrated = !ghost && share > CONCENTRATED;
      const geo = new THREE.BoxGeometry(SLAB, 1, SLAB);
      const mat = ghost
        ? new THREE.MeshBasicMaterial({ color: line, wireframe: true, transparent: true, opacity: 0.55 })
        : new THREE.MeshStandardMaterial({ color: concentrated ? red : orange, roughness: 0.55, metalness: 0.05 });
      const mesh = new THREE.Mesh(geo, mat);
      const x = (col - (cols - 1) / 2) * pitch;
      const z = (row - (rows - 1) / 2) * pitch;
      mesh.position.set(x, 0, z);
      mesh.scale.y = reduced ? h : 0.001;
      mesh.position.y = (reduced ? h : 0.001) / 2;
      group.add(mesh);
      if (!ghost) {
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.55 }));
        mesh.add(edges);
      }
      const tag = label(d.name.replace(/\.(NS|BO)$/i, ""), text);
      tag.position.set(x, 0.05, z + SLAB / 2 + 0.28);
      group.add(tag);
      slabs.push({ mesh, h, delay: i * 0.09, name: d.name, pct: share * 100, tag });
    });

    // hover
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pointer = { x: 0, y: 0 };
    let hovered: number | null = null;
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      const nx = ((e.clientX - r.left) / r.width) * 2 - 1;
      const ny = -((e.clientY - r.top) / r.height) * 2 + 1;
      pointer.x = nx;
      pointer.y = ny;
      if (ghost) return;
      ndc.set(nx, ny);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(slabs.map((s) => s.mesh), false)[0];
      const idx = hit ? slabs.findIndex((s) => s.mesh === hit.object) : -1;
      hovered = idx >= 0 ? idx : null;
      setHover(idx >= 0 ? { name: slabs[idx].name, pct: slabs[idx].pct } : null);
    };
    const onLeave = () => {
      pointer.x = pointer.y = 0;
      hovered = null;
      setHover(null);
    };
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    const resize = () => {
      const w = el.clientWidth || 600;
      const h = el.clientHeight || 360;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = `${w}px`;
      renderer.domElement.style.height = `${h}px`;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    const start = performance.now();
    let last = start;
    let raf = 0;
    let visible = true;
    const look = new THREE.Vector3(0, 0.7, 0);
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      const dt = (now - last) / 1000;
      last = now;
      const t = (now - start) / 1000;
      if (!reduced) {
        group.rotation.y += dt * 0.12;
        // camera leans toward the pointer: depth parallax
        camera.position.x += (2.9 + pointer.x * 0.8 - camera.position.x) * 0.06;
        camera.position.y += (2.5 + pointer.y * 0.4 - camera.position.y) * 0.06;
      }
      camera.lookAt(look);
      ring.scale.setScalar(1 + 0.03 * Math.sin(t * 1.4));
      dustSeed.forEach((d, i) => {
        const a = d.a + (reduced ? 0 : t * d.s * 0.35);
        dustPos[i * 3] = Math.cos(a) * d.r;
        dustPos[i * 3 + 1] = (d.y + (reduced ? 0 : t * 0.12 * d.s)) % 2.6;
        dustPos[i * 3 + 2] = Math.sin(a) * d.r;
      });
      dustGeo.attributes.position.needsUpdate = true;
      slabs.forEach((s, i) => {
        const k = reduced ? 1 : easeOut((t - 0.25 - s.delay) / 0.9);
        const lift = hovered === i ? 1.06 : 1;
        const target = Math.max(0.001, s.h * k * lift);
        s.mesh.scale.y += (target - s.mesh.scale.y) * (reduced ? 1 : 0.2);
        s.mesh.position.y = s.mesh.scale.y / 2;
        s.tag.material.opacity = k;
      });
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
        (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => {
          (x as THREE.SpriteMaterial).map?.dispose?.();
          x.dispose();
        });
      });
      disposeRenderer(renderer);
    };
  }, [slices, ghost, supported, themeTick]);

  if (!supported) {
    return (
      <div className="surface3d-fallback" role="status">
        The 3D holdings view needs WebGL, which isn&apos;t available here.
      </div>
    );
  }
  return (
    <>
      <div ref={host} className="hero-3d-canvas" data-testid="holdings3d" />
      {ghost && <span className="hero-3d-badge">SYNTHETIC PREVIEW</span>}
      <div className="hero-3d-readout" aria-live="off">
        {hover ? (
          <>
            <b>{hover.name}</b> · {hover.pct.toFixed(1)}% of book
            {hover.pct > CONCENTRATED * 100 ? " · concentrated" : ""}
          </>
        ) : ghost ? (
          <>Run an analysis to build your book here.</>
        ) : (
          <>Height = share of the book · hover a slab</>
        )}
      </div>
    </>
  );
}

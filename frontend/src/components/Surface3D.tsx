import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { disposeRenderer, webglAvailable } from "../lib/webgl";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { formatMetric, normalise, rampColor, valueAt } from "../lib/surface";
import type { SurfaceData } from "../lib/surface";

interface Props {
  data: SurfaceData;
  /** the option the user is pricing, marked on the surface */
  marker: { spot: number; days: number };
}

const WIDTH = 2; // world units across spot
const DEPTH = 1.5; // across days
const HEIGHT = 0.9; // value axis

function cssColor(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}


function labelSprite(text: string, color: string): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.font = "700 30px 'Geist Mono Variable', monospace";
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 128, 32);
  const tex = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  sprite.scale.set(0.72, 0.18, 1);
  return sprite;
}

/**
 * Interactive 3D surface of an option metric over spot x days-to-expiry. Drag to orbit, scroll to
 * zoom, hover to read a value. Renders only while on screen, drifts slowly unless the user prefers
 * reduced motion, and falls back to a message where WebGL is unavailable.
 */
export default function Surface3D({ data, marker }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ spot: number; days: number; value: number } | null>(null);
  const [supported] = useState(webglAvailable);
  const [themeTick, setThemeTick] = useState(0);

  // Rebuild colours when the light/dark toggle flips.
  useEffect(() => {
    const obs = new MutationObserver(() => setThemeTick((t) => t + 1));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const el = host.current;
    if (!el || !supported) return;

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const textColor = cssColor("--text-secondary", "#a8a19b");
    const gridColor = cssColor("--border-medium", "rgba(255,255,255,0.12)");
    const accent = cssColor("--accent-2", "#ff8a1f");

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    el.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);
    camera.position.set(1.75, 1.25, 2.05);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = !reduced;
    controls.maxPolarAngle = Math.PI * 0.49; // never go under the floor
    controls.minDistance = 1.2;
    controls.maxDistance = 7;
    controls.autoRotate = !reduced;
    controls.autoRotateSpeed = 0.5;
    controls.target.set(0, 0.3, 0);

    const nx = data.spots.length;
    const nz = data.days.length;
    const geo = new THREE.PlaneGeometry(WIDTH, DEPTH, nx - 1, nz - 1);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position as THREE.BufferAttribute;
    const colors = new Float32Array(pos.count * 3);
    // PlaneGeometry vertex order: row-major over (z, x), z increasing with the row index.
    for (let i = 0; i < nz; i++) {
      for (let j = 0; j < nx; j++) {
        const k = i * nx + j;
        const t = normalise(data.values[i][j], data.min, data.max);
        pos.setY(k, t * HEIGHT);
        const [r, g, b] = rampColor(t);
        colors[k * 3] = r;
        colors[k * 3 + 1] = g;
        colors[k * 3 + 2] = b;
      }
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    // Flat bands: un-index the mesh and give every triangle one colour (the band of its mean height),
    // so nothing is blended across vertices.
    const flat = geo.toNonIndexed();
    const fpos = flat.attributes.position as THREE.BufferAttribute;
    const fcol = new Float32Array(fpos.count * 3);
    for (let v = 0; v < fpos.count; v += 3) {
      const mean = (fpos.getY(v) + fpos.getY(v + 1) + fpos.getY(v + 2)) / 3 / HEIGHT;
      const [r, g, b] = rampColor(mean);
      for (let k = 0; k < 3; k++) fcol.set([r, g, b], (v + k) * 3);
    }
    flat.setAttribute("color", new THREE.BufferAttribute(fcol, 3));
    flat.computeVertexNormals();
    const mesh = new THREE.Mesh(
      flat,
      new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide }),
    );
    scene.add(mesh);
    const wire = new THREE.Mesh(
      geo,
      new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true, transparent: true, opacity: 0.07 }),
    );
    scene.add(wire);

    const grid = new THREE.GridHelper(WIDTH, 10, new THREE.Color(gridColor), new THREE.Color(gridColor));
    grid.scale.z = DEPTH / WIDTH;
    grid.position.y = -0.005;
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.5;
    scene.add(grid);

    const sprites: THREE.Sprite[] = [];
    const addLabel = (text: string, x: number, y: number, z: number) => {
      const s = labelSprite(text, textColor);
      s.position.set(x, y, z);
      scene.add(s);
      sprites.push(s);
    };
    const spotLo = data.spots[0];
    const spotHi = data.spots[nx - 1];
    const dayHi = data.days[nz - 1];
    addLabel(spotLo.toFixed(0), -WIDTH / 2, 0, DEPTH / 2 + 0.2);
    addLabel("spot", 0, 0, DEPTH / 2 + 0.28);
    addLabel(spotHi.toFixed(0), WIDTH / 2, 0, DEPTH / 2 + 0.2);
    addLabel("1d", WIDTH / 2 + 0.25, 0, -DEPTH / 2);
    addLabel("days", WIDTH / 2 + 0.3, 0, 0);
    addLabel(`${dayHi.toFixed(0)}d`, WIDTH / 2 + 0.25, 0, DEPTH / 2);
    addLabel(formatMetric(data.metric, data.max), -WIDTH / 2 - 0.2, HEIGHT, -DEPTH / 2);
    addLabel(formatMetric(data.metric, data.min), -WIDTH / 2 - 0.2, 0.02, -DEPTH / 2);

    if (data.strike >= spotLo && data.strike <= spotHi) {
      const sx = ((data.strike - spotLo) / (spotHi - spotLo) - 0.5) * WIDTH;
      const plane = new THREE.Mesh(
        new THREE.PlaneGeometry(DEPTH, HEIGHT),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(accent), transparent: true, opacity: 0.08, side: THREE.DoubleSide }),
      );
      plane.rotation.y = Math.PI / 2;
      plane.position.set(sx, HEIGHT / 2, 0);
      scene.add(plane);
    }

    const mv = valueAt(data, marker.spot, marker.days);
    let markerMesh: THREE.Mesh | null = null;
    if (mv !== null) {
      const mx = ((marker.spot - spotLo) / (spotHi - spotLo) - 0.5) * WIDTH;
      const mz = ((marker.days - data.days[0]) / (dayHi - data.days[0]) - 0.5) * DEPTH;
      const my = normalise(mv, data.min, data.max) * HEIGHT;
      markerMesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.035, 24, 16),
        new THREE.MeshBasicMaterial({ color: new THREE.Color(accent) }),
      );
      markerMesh.position.set(mx, my + 0.04, mz);
      scene.add(markerMesh);
      const stem = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(mx, 0, mz), new THREE.Vector3(mx, my + 0.04, mz)]),
        new THREE.LineBasicMaterial({ color: new THREE.Color(accent), transparent: true, opacity: 0.6 }),
      );
      scene.add(stem);
    }

    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObject(mesh)[0];
      if (!hit) return setHover(null);
      const spot = spotLo + ((hit.point.x / WIDTH + 0.5) * (spotHi - spotLo));
      const days = data.days[0] + ((hit.point.z / DEPTH + 0.5) * (dayHi - data.days[0]));
      const value = valueAt(data, spot, days);
      setHover(value === null ? null : { spot, days, value });
    };
    const onLeave = () => setHover(null);
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

    let raf = 0;
    let visible = true;
    let t0 = performance.now();
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      controls.update();
      if (markerMesh && !reduced) markerMesh.scale.setScalar(1 + 0.25 * Math.sin((now - t0) / 380));
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(loop);
    const io = new IntersectionObserver(([entry]) => (visible = entry.isIntersecting), { threshold: 0.01 });
    io.observe(el);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      controls.dispose();
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
      t0 = 0;
    };
  }, [data, marker.spot, marker.days, supported, themeTick]);

  if (!supported) {
    return (
      <div className="surface3d-fallback" role="status">
        3D view needs WebGL, which isn&apos;t available here. The price calculator above still works.
      </div>
    );
  }
  return (
    <div className="surface3d">
      <div ref={host} className="surface3d-canvas" data-testid="surface3d" />
      <div className="surface3d-readout" aria-live="off">
        {hover ? (
          <>
            spot <b>{hover.spot.toFixed(2)}</b> · <b>{hover.days.toFixed(0)}</b>d · {data.metric}{" "}
            <b>{formatMetric(data.metric, hover.value)}</b>
          </>
        ) : (
          <>drag to orbit · scroll to zoom · hover to read</>
        )}
      </div>
    </div>
  );
}

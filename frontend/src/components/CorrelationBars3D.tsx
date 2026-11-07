import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import "../styles/chart.css";
import { disposeRenderer, webglAvailable } from "../lib/webgl";

export interface CorrelationMatrix {
  title?: string;
  labels: string[];
  values: number[][];
}

const SIZE = 2; // world units across the grid
const HEIGHT = 0.8; // bar height for |corr| = 1

/** Diverging colour for a correlation: teal for negative, near-black at zero, orange for positive. */
export function correlationColor(v: number): [number, number, number] {
  const t = Math.min(1, Math.abs(v));
  const lo: [number, number, number] = [0.12, 0.1, 0.12];
  const hi: [number, number, number] = v >= 0 ? [1.0, 0.54, 0.12] : [0.17, 0.83, 0.75];
  return [lo[0] + (hi[0] - lo[0]) * t, lo[1] + (hi[1] - lo[1]) * t, lo[2] + (hi[2] - lo[2]) * t];
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
  ctx.fillText(text.slice(0, 10), 128, 32);
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false }),
  );
  sprite.scale.set(0.5, 0.125, 1);
  return sprite;
}

/** Plain table of the same matrix, shown when WebGL is unavailable. */
function HeatTable({ matrix }: { matrix: CorrelationMatrix }) {
  return (
    <table className="corr-table">
      <thead>
        <tr>
          <th />
          {matrix.labels.map((l) => (
            <th key={l}>{l}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {matrix.values.map((row, i) => (
          <tr key={matrix.labels[i]}>
            <th scope="row">{matrix.labels[i]}</th>
            {row.map((v, j) => {
              const [r, g, b] = correlationColor(v);
              return (
                <td key={j} style={{ background: `rgb(${r * 255 | 0} ${g * 255 | 0} ${b * 255 | 0} / 0.55)` }}>
                  {v.toFixed(2)}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Interactive 3D bar chart of a correlation matrix. Drag to orbit, hover to read a pair. */
export default function CorrelationBars3D({ matrix }: { matrix: CorrelationMatrix }) {
  const host = useRef<HTMLDivElement>(null);
  const [supported] = useState(webglAvailable);
  const [hover, setHover] = useState<{ a: string; b: string; v: number } | null>(null);
  const n = matrix.labels.length;

  useEffect(() => {
    const el = host.current;
    if (!el || !supported || n < 2) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const textColor = getComputedStyle(document.documentElement).getPropertyValue("--text-secondary").trim() || "#a8a19b";

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.style.display = "block";
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);
    camera.position.set(2.7, 2.1, 3.1);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = !reduced;
    controls.autoRotate = !reduced;
    controls.autoRotateSpeed = 0.6;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minDistance = 1.5;
    controls.maxDistance = 7;
    controls.target.set(0, 0.2, 0);

    const cell = SIZE / n;
    const bars: THREE.Mesh[] = [];
    const info = new Map<THREE.Object3D, { a: string; b: string; v: number }>();
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const v = matrix.values[i][j];
        const h = Math.max(0.015, Math.abs(v) * HEIGHT);
        const mesh = new THREE.Mesh(
          new THREE.BoxGeometry(cell * 0.82, h, cell * 0.82),
          new THREE.MeshBasicMaterial({ color: new THREE.Color(...correlationColor(v)) }),
        );
        mesh.position.set((j + 0.5) * cell - SIZE / 2, v >= 0 ? h / 2 : -h / 2, (i + 0.5) * cell - SIZE / 2);
        scene.add(mesh);
        bars.push(mesh);
        info.set(mesh, { a: matrix.labels[i], b: matrix.labels[j], v });
      }
    }
    const grid = new THREE.GridHelper(SIZE, n, 0x888888, 0x888888);
    (grid.material as THREE.Material).transparent = true;
    (grid.material as THREE.Material).opacity = 0.25;
    scene.add(grid);
    matrix.labels.forEach((label, k) => {
      const x = labelSprite(label, textColor);
      x.position.set((k + 0.5) * cell - SIZE / 2, 0, SIZE / 2 + 0.16);
      const z = labelSprite(label, textColor);
      z.position.set(-SIZE / 2 - 0.3, 0, (k + 0.5) * cell - SIZE / 2);
      scene.add(x, z);
    });

    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(bars)[0];
      setHover(hit ? (info.get(hit.object) ?? null) : null);
    };
    const onLeave = () => setHover(null);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    const resize = () => {
      const w = el.clientWidth || 480;
      const h = el.clientHeight || 300;
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
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      controls.update();
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
    };
  }, [matrix, n, supported]);

  if (!supported || n < 2) return <HeatTable matrix={matrix} />;
  return (
    <div className="surface3d corr3d">
      <div ref={host} className="surface3d-canvas" data-testid="corr3d" />
      <div className="surface3d-readout" aria-live="off">
        {hover ? (
          <>
            {hover.a} / {hover.b} <b>{hover.v.toFixed(2)}</b>
          </>
        ) : (
          <>drag to orbit Â· hover a bar Â· orange = move together, teal = opposite</>
        )}
      </div>
    </div>
  );
}

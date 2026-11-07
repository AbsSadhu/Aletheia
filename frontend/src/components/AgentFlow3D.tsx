import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

import type { StepStatus } from "../lib/runProgress";
import { disposeRenderer, webglAvailable } from "../lib/webgl";

interface Props {
  steps: { key: string; label: string; status: StepStatus }[];
}

const PITCH = 1.7;
const BLOCK = 0.9;

function cssColor(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function tag(text: string, color: string): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = 320;
  c.height = 64;
  const ctx = c.getContext("2d")!;
  ctx.font = "700 30px 'Geist Variable', sans-serif";
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 160, 32);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
  s.scale.set(1.25, 0.25, 1);
  return s;
}

/**
 * The five agents as blocks on a rail. Completed blocks are solid orange, the active block stands
 * up in red with a packet travelling the rail into it, pending blocks are outlines. Status changes
 * ease the blocks to their new height; nothing is rebuilt.
 */
export default function AgentFlow3D({ steps }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [supported] = useState(webglAvailable);
  const status = useRef(steps);
  status.current = steps;
  const labels = steps.map((s) => s.label).join("|");

  useEffect(() => {
    const el = host.current;
    if (!el || !supported) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const orange = new THREE.Color(cssColor("--accent-2", "#ff7a00"));
    const red = new THREE.Color(cssColor("--accent", "#ff2b1c"));
    const dim = new THREE.Color(cssColor("--bg-elevated", "#1a1a1a"));
    const line = new THREE.Color(cssColor("--border-medium", "#333333"));
    const text = cssColor("--text-secondary", "#a39d98");

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.domElement.style.display = "block";
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 50);
    camera.position.set(0.8, 3.2, 6.2);
    const look = new THREE.Vector3(0, 0.3, 0);
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const key = new THREE.DirectionalLight(0xffffff, 2);
    key.position.set(2, 5, 3);
    scene.add(key);

    const n = steps.length;
    const x0 = -((n - 1) * PITCH) / 2;
    const rail = new THREE.Mesh(
      new THREE.BoxGeometry((n - 1) * PITCH + BLOCK, 0.05, 0.12),
      new THREE.MeshStandardMaterial({ color: line, roughness: 1 }),
    );
    rail.position.set(0, -0.025, 0);
    scene.add(rail);

    const blocks = steps.map((s, i) => {
      const geo = new THREE.BoxGeometry(BLOCK, 1, BLOCK);
      const mat = new THREE.MeshStandardMaterial({ color: dim, roughness: 0.55 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(x0 + i * PITCH, 0.2, 0);
      mesh.scale.y = 0.4;
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.5 }));
      mesh.add(edges);
      scene.add(mesh);
      const t = tag(s.label, text);
      t.position.set(x0 + i * PITCH, -0.3, 0.9);
      scene.add(t);
      return { mesh, mat, h: 0.4 };
    });

    const packet = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.2, 0.2), new THREE.MeshStandardMaterial({ color: red }));
    scene.add(packet);

    const pointer = { x: 0 };
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    };
    renderer.domElement.addEventListener("pointermove", onMove);

    const resize = () => {
      const w = el.clientWidth || 600;
      const h = el.clientHeight || 210;
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
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      const t = (now - t0) / 1000;
      const cur = status.current;
      let activeIdx = -1;
      blocks.forEach((b, i) => {
        const st = cur[i]?.status ?? "pending";
        if (st === "active") activeIdx = i;
        const targetH = st === "active" ? 1.5 : st === "completed" ? 0.9 : st === "failed" ? 0.55 : 0.4;
        const pulse = st === "active" && !reduced ? 0.06 * Math.sin(t * 4) : 0;
        b.h += (targetH + pulse - b.h) * (reduced ? 1 : 0.12);
        b.mesh.scale.y = b.h;
        b.mesh.position.y = b.h / 2;
        const col = st === "active" || st === "failed" ? red : st === "completed" ? orange : dim;
        b.mat.color.lerp(col, reduced ? 1 : 0.15);
      });
      // packet rides the rail into the active block
      if (activeIdx > 0) {
        const f = reduced ? 1 : (t * 0.9) % 1;
        packet.visible = true;
        packet.position.set(x0 + (activeIdx - 1 + f) * PITCH, 0.14, 0);
      } else packet.visible = false;
      if (!reduced) camera.position.x += (0.8 + pointer.x * 0.8 - camera.position.x) * 0.05;
      camera.lookAt(look);
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
    // labels only: status changes are read from the ref, so the scene is never rebuilt on progress
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supported, labels]);

  if (!supported) {
    return (
      <ol className="agentflow-fallback" aria-label="Agent progress">
        {steps.map((s) => (
          <li key={s.key} style={{ color: s.status === "pending" ? "var(--text-muted)" : "var(--text-primary)" }}>
            {s.label}: {s.status}
          </li>
        ))}
      </ol>
    );
  }
  return (
    <div className="agentflow">
      <div ref={host} className="agentflow-canvas" data-testid="agentflow3d" role="img" aria-label={`Agent progress: ${steps.map((s) => `${s.label} ${s.status}`).join(", ")}`} />
    </div>
  );
}

import { animate } from "motion";
import { useEffect, useRef, useState } from "react";

interface Props {
  value: number;
  format?: (n: number) => string;
  /** animation length in ms */
  duration?: number;
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);

/** A number that eases from its previous value to the new one. Snaps when motion is reduced. */
export default function CountUp({ value, format = (n) => String(Math.round(n)), duration = 700 }: Props) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);

  useEffect(() => {
    if (prefersReducedMotion() || from.current === value) {
      from.current = value;
      setShown(value);
      return;
    }
    const controls = animate(from.current, value, {
      duration: duration / 1000,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        from.current = v;
        setShown(v);
      },
    });
    return () => controls.stop();
  }, [value, duration]);

  return <>{format(shown)}</>;
}

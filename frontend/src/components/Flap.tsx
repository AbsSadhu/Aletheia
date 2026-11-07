import { useEffect, useRef, useState } from "react";

interface Props {
  text: string;
  /** hold changed characters in the alert colour for a few seconds (default true) */
  hold?: boolean;
  className?: string;
}

/**
 * Text set in split-flap cells. When the text changes, only the characters that changed flip,
 * left to right, and stay in the alert colour for a moment (the departure-board "this changed"
 * signal). The first render is static. Screen readers get the plain string.
 */
export default function Flap({ text, hold = true, className = "" }: Props) {
  const prev = useRef<string | null>(null);
  const [changed, setChanged] = useState<Set<number>>(new Set());

  useEffect(() => {
    const before = prev.current;
    prev.current = text;
    if (before === null || before === text) return;
    const next = new Set<number>();
    [...text].forEach((ch, i) => {
      if (before[i] !== ch) next.add(i);
    });
    setChanged(next);
  }, [text]);

  return (
    <span className={`flap ${className}`} role="img" aria-label={text}>
      {[...text].map((ch, i) => {
        const isChanged = changed.has(i);
        const cls = ["flap-cell", ch === " " ? "is-space" : "", isChanged ? (hold ? "held" : "flipped") : ""]
          .filter(Boolean)
          .join(" ");
        return (
          <span
            // re-key a changed cell on its character so the animation restarts
            key={isChanged ? `${i}-${ch}` : i}
            className={cls}
            style={{ ["--i" as string]: i } as React.CSSProperties}
            aria-hidden="true"
          >
            {ch === " " ? " " : ch}
          </span>
        );
      })}
    </span>
  );
}

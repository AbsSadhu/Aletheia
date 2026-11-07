import type { ReactNode } from "react";

import Lattice3D from "./Lattice3D";
import type { LatticeVariant } from "./Lattice3D";

interface Props {
  /** the page's one-line promise, in display type */
  headline: string;
  /** a sentence of context */
  sub?: string;
  variant?: LatticeVariant;
  /** controls or figures that sit under the headline */
  children?: ReactNode;
}

/**
 * The band at the top of a page: a headline and its context on the left, a rolling 3D field on the
 * right. The headline says what the page is for, not what it is called (the top bar already does).
 */
export default function PageHero({ headline, sub, variant = "wave", children }: Props) {
  return (
    <section className="page-hero">
      <div className="page-hero-copy">
        <h2 className="page-hero-headline">{headline}</h2>
        {sub && <p className="page-hero-sub">{sub}</p>}
        {children && <div className="page-hero-body">{children}</div>}
      </div>
      <div className="page-hero-scene">
        <Lattice3D variant={variant} />
      </div>
    </section>
  );
}

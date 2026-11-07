import { Link, useInRouterContext } from "react-router-dom";
import type { AnchorHTMLAttributes } from "react";

/** A router link where there is a router, a plain anchor where there is not (isolated component tests). */
export default function SafeLink({ to, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) {
  const inRouter = useInRouterContext();
  return inRouter ? <Link to={to} {...rest} /> : <a href={to} {...rest} />;
}

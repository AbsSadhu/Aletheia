import { forwardRef } from "react";
import type { AnchorHTMLAttributes } from "react";
import { Link } from "react-router-dom";

/**
 * Adapter so Astryx navigation components (which hand their link component an `href`) navigate
 * with react-router instead of reloading the page.
 */
const RouterLink = forwardRef<HTMLAnchorElement, AnchorHTMLAttributes<HTMLAnchorElement> & { href?: string }>(
  function RouterLink({ href, ...rest }, ref) {
    return <Link ref={ref} to={href ?? "#"} {...rest} />;
  },
);

export default RouterLink;

import React, {type ReactNode} from 'react';

import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';

export default function NavbarLogo(): ReactNode {
  const logoUrl = useBaseUrl('/img/cohortome-logo.svg');

  return (
    <Link className="navbar__brand" to="/" aria-label="COHORTome home">
      <img className="cohortomeNavbarIcon" src={logoUrl} alt="" />
      <span className="navbar__title cohortomeNavbarWordmark" aria-hidden="true">
        <span className="cohortomeNavbarPrimary">COHORT</span>
        <span className="cohortomeNavbarSecondary">ome</span>
      </span>
    </Link>
  );
}

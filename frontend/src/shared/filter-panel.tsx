import { useId } from 'react';
import type { ReactNode } from 'react';

export function FilterPanel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  const titleId = useId();
  return (
    <section className={`ui-filter-panel ${className}`} aria-labelledby={titleId}>
      <h3 id={titleId}>Filter patients</h3>
      {children}
    </section>
  );
}

import type { MouseEventHandler, ReactNode } from 'react';

type ViewStatusProps = {
  children: ReactNode;
  kind?: 'loading' | 'empty' | 'error';
  onRetry?: MouseEventHandler<HTMLButtonElement>;
  retryLabel?: string;
  retryId?: string;
};

// Render plain text, never HTML. Keep recovery next to the failed operation.
export function ViewStatus({
  children,
  kind = 'empty',
  onRetry,
  retryLabel = 'Retry',
  retryId,
}: ViewStatusProps) {
  return (
    <div className={`ui-view-status ui-view-status--${kind}`} role="status">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" />
        {kind === 'loading' ? <path d="M12 6v6l4 2" /> : <path d="M12 7v6m0 3v1" />}
      </svg>
      <span>{children}</span>
      {onRetry && (
        <button type="button" className="query-chip" id={retryId} onClick={onRetry}>
          {retryLabel}
        </button>
      )}
    </div>
  );
}

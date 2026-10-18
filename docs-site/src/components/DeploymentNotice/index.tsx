import type {ReactNode} from 'react';
import Admonition from '@theme/Admonition';

type Props = {
  mode: 'desktop' | 'web' | 'both';
  title?: string;
  children: ReactNode;
};

function DeploymentIcon({web = false}: {web?: boolean}) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" style={{fill: 'none', flexShrink: 0}}
      stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" focusable="false">
      {web ? <>
        <circle cx="12" cy="12" r="9" />
        <ellipse cx="12" cy="12" rx="4" ry="9" />
        <path d="M3 12h18" />
      </> : <>
        <rect x="3" y="3" width="18" height="13" rx="2" />
        <path d="M12 16v5M8 21h8" />
      </>}
    </svg>
  );
}

export default function DeploymentNotice({mode, title, children}: Props) {
  const label = mode === 'both' ? 'Desktop and Web' : mode === 'web' ? 'Web' : 'Desktop';
  return (
    <Admonition type="info" title={title || label} icon={
      <span style={{display: 'inline-flex', gap: '0.35rem', verticalAlign: 'middle'}}>
        {mode !== 'web' && <DeploymentIcon />}
        {mode !== 'desktop' && <DeploymentIcon web />}
      </span>
    }>
      {children}
    </Admonition>
  );
}

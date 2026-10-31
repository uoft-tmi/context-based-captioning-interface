import type { ReactNode, SVGProps } from 'react';

type IconName = 'captions' | 'mic' | 'file' | 'arrow' | 'check' | 'upload' | 'download' | 'expand' | 'close' | 'stop' | 'info' | 'logout' | 'chevron';

export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    captions: <><rect x="3" y="4" width="18" height="16" rx="4" /><path d="M7 10h4m3 0h3M7 14h2m3 0h5" /></>,
    mic: <><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8" /></>,
    file: <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8m-8 4h5" />,
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    check: <path d="m5 12 4 4L19 6" />,
    upload: <path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" />,
    download: <path d="M12 3v13m-5-5 5 5 5-5M4 17v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />,
    expand: <path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v.01" /></>,
    logout: <path d="M9 4H4v16h5m5-13 5 5-5 5m-6-5h11" />,
    chevron: <path d="m9 5 7 7-7 7" />,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}

export function Brand() {
  return <div className="brand"><span className="brand-mark"><Icon name="captions" width="25" height="25" /></span><span>Lecture<span className="brand-light"> Captioning</span></span></div>;
}

export function Steps({ current }: { current: number }) {
  return <nav aria-label="Lecture progress"><ol className="steps">{['Create session', 'Session details', 'Recording', 'Transcript'].map((label, index) => <li key={label} className={index === current ? 'current' : index < current ? 'done' : ''} aria-current={index === current ? 'step' : undefined}><span className="step-number">{index < current ? <Icon name="check" width="14" height="14" /> : index + 1}</span><span>{label}</span>{index < 3 && <span className="step-line" />}</li>)}</ol></nav>;
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'error' | 'warning' }) {
  return <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}><Icon name="info" /><div>{children}</div></div>;
}

export function Loading({ children = 'Loading your workspace…' }: { children?: ReactNode }) {
  return <div className="loading-state" role="status"><span className="spinner" />{children}</div>;
}

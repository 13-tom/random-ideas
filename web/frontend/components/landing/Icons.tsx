type IconProps = { className?: string };

export function IconWand({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <path d="M4 20L18 6" strokeLinecap="round" />
      <path d="M15 3l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2z" strokeLinejoin="round" />
      <path d="M19 10l.6 1.4L21 12l-1.4.6L19 14l-.6-1.4L17 12l1.4-.6L19 10z" strokeLinejoin="round" />
    </svg>
  );
}

export function IconCrop({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <path d="M6 2v14a2 2 0 002 2h14" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 22V8a2 2 0 00-2-2H2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconCaptions({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
      <path d="M6.5 14.5h3M6.5 11.5h5M13 14.5h4.5M15.5 11.5h2" strokeLinecap="round" />
    </svg>
  );
}

export function IconUpload({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <path d="M12 16V4M12 4l-4.5 4.5M12 4l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 16v2.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V16" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconSparkle({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <path d="M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6L12 3z" strokeLinejoin="round" />
    </svg>
  );
}

export function IconDownload({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <path d="M12 4v12M12 16l-4.5-4.5M12 16l4.5-4.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 18v1.5A1.5 1.5 0 005.5 21h13a1.5 1.5 0 001.5-1.5V18" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconFace({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9 10h.01M15 10h.01M8.5 15c1 1 2.2 1.5 3.5 1.5s2.5-.5 3.5-1.5" strokeLinecap="round" />
    </svg>
  );
}

export function IconGlobe({ className = "h-6 w-6" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={1.6}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.6 3.8 5.7 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3z" />
    </svg>
  );
}

export function IconCheck({ className = "h-5 w-5" }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} stroke="currentColor" strokeWidth={2}>
      <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

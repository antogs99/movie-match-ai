'use client';

declare global {
  interface Window {
    gtag: (...args: any[]) => void;
  }
}

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';

export function AnalyticsWrapper() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    const url = `${pathname}?${searchParams.toString()}`;

    window.gtag('config', 'G-LQ8Q32DZET', {
      page_path: url,
    });
  }, [pathname, searchParams]);

  return null;
}
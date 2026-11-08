'use client';

import { SessionProvider } from 'next-auth/react';
import { useMemo } from 'react';
import { SpacetimeDBProvider } from 'spacetimedb/react';
import { createSpacetimeConnectionBuilder } from '@/lib/spacetime';

export function Providers({ children }: { children: React.ReactNode }) {
  const connectionBuilder = useMemo(() => createSpacetimeConnectionBuilder(), []);

  return (
    <SessionProvider>
      <SpacetimeDBProvider connectionBuilder={connectionBuilder}>
        {children}
      </SpacetimeDBProvider>
    </SessionProvider>
  );
}

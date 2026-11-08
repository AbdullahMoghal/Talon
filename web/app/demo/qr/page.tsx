'use client';

import { Suspense } from 'react';
import { QrPanel } from '@/components/demo/qr-panel';

export default function QrPage() {
  return (
    <Suspense fallback={null}>
      <QrPanel />
    </Suspense>
  );
}

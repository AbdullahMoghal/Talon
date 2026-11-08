'use client';

import { AppShell } from '@/components/app-shell';
import { ScamCatalog } from '@/components/scam-catalog';
import './catalog.css';

export default function CatalogPage() {
  return (
    <AppShell>
      <ScamCatalog />
    </AppShell>
  );
}

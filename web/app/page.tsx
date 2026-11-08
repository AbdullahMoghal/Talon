'use client';

import { AppShell } from '@/components/app-shell';
import { DatasetDashboard } from '@/components/dataset-dashboard';

export default function Home() {
  return (
    <AppShell>
      <div className="app-content">
        <DatasetDashboard />
      </div>
    </AppShell>
  );
}

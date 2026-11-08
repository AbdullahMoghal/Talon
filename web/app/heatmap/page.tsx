'use client';

import { AppShell } from '@/components/app-shell';
import { ScammerHeatmap } from '@/components/scammer-heatmap';

export default function HeatmapPage() {
  return (
    <AppShell>
      <ScammerHeatmap />
    </AppShell>
  );
}

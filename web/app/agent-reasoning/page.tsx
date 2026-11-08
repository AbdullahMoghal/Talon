'use client';

import { Suspense } from 'react';
import { AppShell } from '@/components/app-shell';
import { AgentReasoning } from '@/components/demo/agent-reasoning';
import '../demo/demo.css';

export default function AgentReasoningPage() {
  return (
    <AppShell dark>
      <Suspense fallback={null}>
        <AgentReasoning />
      </Suspense>
    </AppShell>
  );
}

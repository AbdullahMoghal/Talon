'use client';

import { useMemo } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { LiveDashboard } from './live-dashboard';
import { cleanRoom, ms } from './demo-data';

/**
 * The "Agent Reasoning" tab of the main dashboard: the live agent view for a demo room.
 * Defaults to the newest open room; ?room= picks one explicitly.
 */
export function AgentReasoning() {
  const [rooms, ready] = useTable(tables.demoRoom);
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  // Second-customer rooms (CODE-2) belong to their main room, so they aren't listed.
  const open = useMemo(
    () => rooms.filter((r) => r.status === 'open' && !r.code.endsWith('-2')).sort((a, b) => ms(b.createdAt) - ms(a.createdAt)),
    [rooms]
  );
  const room = cleanRoom(params.get('room')) || open[0]?.code;

  return (
    <div className="demo-root reasoning-tab">
      <div className="reasoning-bar">
        <label>
          Room
          <select value={room ?? ''} onChange={(e) => router.replace(`${pathname}?room=${e.target.value}`)}>
            {!room && <option value="">{ready ? 'No open rooms' : 'Loading…'}</option>}
            {room && !open.some((r) => r.code === room) && <option value={room}>{room}</option>}
            {open.map((r) => <option key={r.code} value={r.code}>{r.code}</option>)}
          </select>
        </label>
        {room && (
          <span className="reasoning-links">
            Phones: <a href={`/demo/scammer?room=${room}`} target="_blank" rel="noreferrer">scammer</a> ·{' '}
            <a href={`/demo/phone?room=${room}`} target="_blank" rel="noreferrer">customer</a> ·{' '}
            <a href={`/demo/phone?room=${room}-2`} target="_blank" rel="noreferrer">second customer</a>
          </span>
        )}
      </div>
      {room ? (
        <LiveDashboard room={room} />
      ) : (
        <div className="live">
          <div className="live-banner">
            No demo room is open. Start the engine: <code>python -m talon_agents.live --room DEMO</code>
          </div>
        </div>
      )}
    </div>
  );
}

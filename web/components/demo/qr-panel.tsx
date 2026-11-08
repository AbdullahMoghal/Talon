'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import QRCode from 'qrcode';
import { useTable } from 'spacetimedb/react';
import { tables } from '@/src/module_bindings';
import { cleanRoom, ms } from './demo-data';
import { TalonLogo } from '@/components/talon-logo';

type Card = { key: string; title: string; who: string; path: string; big: boolean };

/**
 * Full-screen QR codes for the live demo: judges scan the scammer and customer phones, the laptop
 * switches to the agent view. Links use this site's own origin, so it works on any domain.
 */
export function QrPanel() {
  const [rooms, ready] = useTable(tables.demoRoom);
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [origin, setOrigin] = useState('');
  const [svgs, setSvgs] = useState<Record<string, string>>({});

  useEffect(() => setOrigin(window.location.origin), []);

  const open = useMemo(
    () => rooms.filter((r) => r.status === 'open' && !r.code.endsWith('-2')).sort((a, b) => ms(b.createdAt) - ms(a.createdAt)),
    [rooms]
  );
  const room = cleanRoom(params.get('room')) || open[0]?.code;

  const cards: Card[] = useMemo(() => (room ? [
    { key: 'scammer', title: 'Phone 1: sender', who: 'Text the other phone. Chat normally, or play a scammer and try to get paid.', path: `/demo/scammer?room=${room}`, big: true },
    { key: 'customer', title: 'Phone 2: customer', who: 'You are the T-Mobile customer. Text normally; Talon watches for scams.', path: `/demo/phone?room=${room}`, big: true },
    { key: 'second', title: 'Second customer', who: 'Optional: see a shut-down scam blocked before it arrives.', path: `/demo/phone?room=${room}-2`, big: false },
  ] : []), [room]);

  useEffect(() => {
    if (!origin) return;
    let cancelled = false;
    Promise.all(cards.map(async (c) => [c.key, await QRCode.toString(`${origin}${c.path}`, { type: 'svg', margin: 1, errorCorrectionLevel: 'M' })] as const))
      .then((pairs) => { if (!cancelled) setSvgs(Object.fromEntries(pairs)); });
    return () => { cancelled = true; };
  }, [cards, origin]);

  return (
    <div className="qr-page">
      <header className="qr-head">
        <TalonLogo height={40} />
        <div>
          <h1><span>T-Mobile Talon</span> live demo</h1>
          <p>Scan with your phone camera. The laptop shows every agent step.</p>
        </div>
        <label className="qr-room">
          Room
          <select value={room ?? ''} onChange={(e) => router.replace(`${pathname}?room=${e.target.value}`)}>
            {!room && <option value="">{ready ? 'No open rooms' : 'Loading…'}</option>}
            {room && !open.some((r) => r.code === room) && <option value={room}>{room}</option>}
            {open.map((r) => <option key={r.code} value={r.code}>{r.code}</option>)}
          </select>
        </label>
      </header>

      {room ? (
        <div className="qr-row">
          {cards.map((c) => (
            <div key={c.key} className={`qr-card ${c.big ? '' : 'qr-small'}`}>
              <h2>{c.title}</h2>
              <div className="qr-code" dangerouslySetInnerHTML={{ __html: svgs[c.key] ?? '' }} />
              <p>{c.who}</p>
              <code>{origin ? `${origin}${c.path}` : c.path}</code>
            </div>
          ))}
        </div>
      ) : (
        <p className="qr-empty">No demo room is open. Start the engine: <code>python -m talon_agents.live --room HACK</code></p>
      )}

      {room && (
        <div className="qr-actions">
          <Link className="qr-go" href={`/demo/live?room=${room}`}>Open the live agent view →</Link>
          <Link className="qr-secondary" href={`/agent-reasoning?room=${room}`}>Agent Reasoning tab</Link>
        </div>
      )}
    </div>
  );
}

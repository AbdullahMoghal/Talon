'use client';

import Link from 'next/link';
import { RoomPage } from './room-page';
import { TalonLogo } from '@/components/talon-logo';

export default function DemoHub() {
  return (
    <RoomPage
      title="Talon live demo"
      render={(room) => (
        <div className="room-form">
          <TalonLogo height={44} />
          <h1>Room {room}</h1>
          <Link className="hub-link" href={`/demo/scammer?room=${room}`}>Scammer phone</Link>
          <Link className="hub-link" href={`/demo/phone?room=${room}`}>Customer phone</Link>
          <Link className="hub-link" href={`/demo/phone?room=${room}-2`}>Second customer</Link>
          <Link className="hub-link primary" href={`/demo/live?room=${room}`}>Live dashboard</Link>
        </div>
      )}
    />
  );
}

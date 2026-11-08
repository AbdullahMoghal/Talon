'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { cleanRoom } from '@/components/demo/demo-data';
import { TalonLogo } from '@/components/talon-logo';

/** Reads ?room= and renders the screen, or asks for a room code. */
export function RoomPage({ render, title }: { render: (room: string) => React.ReactNode; title: string }) {
  return (
    <Suspense fallback={null}>
      <Inner render={render} title={title} />
    </Suspense>
  );
}

function Inner({ render, title }: { render: (room: string) => React.ReactNode; title: string }) {
  const room = cleanRoom(useSearchParams().get('room'));
  if (room) return <>{render(room)}</>;
  return (
    <form className="room-form" method="get">
      <TalonLogo height={44} />
      <h1>{title}</h1>
      <input name="room" placeholder="Room code" autoCapitalize="characters" autoFocus />
      <button type="submit">Join</button>
    </form>
  );
}

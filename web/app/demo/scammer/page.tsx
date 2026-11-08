'use client';

import { ScammerPhone } from '@/components/demo/scammer-phone';
import { RoomPage } from '../room-page';

export default function ScammerPage() {
  return <RoomPage title="Scammer phone" render={(room) => <ScammerPhone room={room} />} />;
}

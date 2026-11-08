'use client';

import { LiveDashboard } from '@/components/demo/live-dashboard';
import { RoomPage } from '../room-page';

export default function LivePage() {
  return <RoomPage title="Live dashboard" render={(room) => <LiveDashboard room={room} />} />;
}

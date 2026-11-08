'use client';

import { CustomerPhone } from '@/components/demo/customer-phone';
import { RoomPage } from '../room-page';

export default function CustomerPage() {
  return <RoomPage title="Customer phone" render={(room) => <CustomerPhone room={room} />} />;
}

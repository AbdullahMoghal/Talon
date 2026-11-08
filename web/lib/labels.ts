/** Human-readable labels for ids from the taxonomy and the indicator kinds. */

export const INDICATOR_KIND_LABELS: Record<string, string> = {
  brand: 'Brands impersonated',
  url: 'Links',
  phone: 'Phone numbers',
  email: 'Email addresses',
  payment_handle: 'Payment handles',
  wallet: 'Crypto wallets',
  giftcard_ask: 'Gift card requests',
  account: 'Bank accounts',
  remote_access_id: 'Remote access codes',
  sender_number: 'Sender numbers',
};

/** "package_delivery" -> "Package delivery". Used only when there's no name in the taxonomy. */
export function humanize(id: string): string {
  const s = id.replace(/_/g, ' ').trim();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

export function labelFor(id: string, names?: Map<string, string>): string {
  return names?.get(id) ?? INDICATOR_KIND_LABELS[id] ?? humanize(id);
}

import type { Metadata, Viewport } from 'next';
import './demo.css';

export const metadata: Metadata = { title: 'Talon live demo' };
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  viewportFit: 'cover',
  themeColor: '#000000',
};

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return <div className="demo-root">{children}</div>;
}

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { signOut, useSession } from 'next-auth/react';
import { TalonLogo } from '@/components/talon-logo';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data } = useSession();
  const pathname = usePathname();
  const name = data?.user?.name || data?.user?.email || 'signed in';

  return (
    <main className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar-left">
          <Link href="/" className="app-brand" aria-label="Talon home">
            <TalonLogo height={26} />
          </Link>
          <nav className="app-nav" aria-label="Primary">
            <Link
              href="/"
              className={`app-nav-link${pathname === '/' ? ' is-active' : ''}`}
            >
              Overview
            </Link>
            <Link
              href="/heatmap"
              className={`app-nav-link${pathname === '/heatmap' ? ' is-active' : ''}`}
            >
              Heatmap
            </Link>
            <Link
              href="/agent-reasoning"
              className={`app-nav-link${pathname === '/agent-reasoning' ? ' is-active' : ''}`}
            >
              Agent Reasoning
            </Link>
            <Link
              href="/catalog"
              className={`app-nav-link${pathname === '/catalog' ? ' is-active' : ''}`}
            >
              Scam Catalog
            </Link>
          </nav>
        </div>
        <div className="app-topbar-actions">
          <Link href="/demo/qr" className="app-qr" title="QR codes for the live demo phones">
            QR codes
          </Link>
          <span className="app-user">{name}</span>
          <button
            type="button"
            className="app-signout"
            onClick={() => void signOut({ callbackUrl: '/login' })}
          >
            Log out
          </button>
        </div>
      </header>
      {children}
    </main>
  );
}

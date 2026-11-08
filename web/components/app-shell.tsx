'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { signOut, useSession } from 'next-auth/react';

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data } = useSession();
  const pathname = usePathname();
  const name = data?.user?.name || data?.user?.email || 'signed in';

  return (
    <main className="app-shell">
      <header className="app-topbar">
        <div className="app-topbar-left">
          <Link href="/" className="app-brand" aria-label="Talon home">
            <span className="login-brand-mark">T</span>
            <span className="login-brand-text">alon</span>
          </Link>
          <nav className="app-nav" aria-label="Primary">
            <Link
              href="/"
              className={`app-nav-link${pathname === '/' ? ' is-active' : ''}`}
            >
              Dataset
            </Link>
            <Link
              href="/heatmap"
              className={`app-nav-link${pathname === '/heatmap' ? ' is-active' : ''}`}
            >
              Heatmap
            </Link>
          </nav>
        </div>
        <div className="app-topbar-actions">
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

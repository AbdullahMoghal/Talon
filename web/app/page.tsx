'use client';

import { signOut, useSession } from 'next-auth/react';

export default function Home() {
  const { data } = useSession();
  const name = data?.user?.name || data?.user?.email || 'signed in';

  return (
    <main className="app-shell">
      <header className="app-topbar">
        <div className="app-brand">
          <span className="login-brand-mark">T</span>
          <span className="login-brand-text">alon</span>
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
      <section className="app-blank" />
    </main>
  );
}
